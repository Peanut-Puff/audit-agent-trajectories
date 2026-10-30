#!/usr/bin/env python3
"""Normalize model rounds and tool calls across Harbor-style trajectory formats."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shlex
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_VERSION = "1.0.0"
SCHEMA_VERSION = "trajectory-events/1"
METHODOLOGY_VERSION = "2.9.0"
RULE_VERSION = "trajectory-event-normalization/1.0"
HASH_LIMIT = 64 * 1024 * 1024

DIRECT_EXPLORATION_TOOLS = {
    "cat", "codesearch", "find", "glob", "grep", "list", "ls", "openfile", "read",
    "readfile", "search", "tree", "view", "viewimage", "webfetch",
}
DIRECT_EDIT_TOOLS = {
    "applypatch", "deletefile", "edit", "multiedit", "patch", "replace", "write", "writefile",
}
DIRECT_VERIFICATION_TOOLS = {
    "benchmark", "build", "check", "compile", "eval", "evaluate", "lint", "test", "verify",
}
EXECUTE_TOOLS = {"bash", "exec", "execcommand", "shell", "terminal"}
POLL_TOOLS = {"poll", "wait", "waitprocess", "writestdin"}
NON_CLASSIFIED_TOOLS = POLL_TOOLS | {"todowrite"}

COMMAND_BOUNDARY = r"(?:^|[;&|]\s*|\n|[\"']\s*)\s*"
COMMAND_PREFIX = (
    r"(?:(?:sudo|env|command)\s+|[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+\s+|"
    r"timeout\s+(?:--\S+\s+)*\S+\s+|(?:uv|poetry|pipenv)\s+run\s+|"
    r"(?:npx|corepack)\s+|docker\s+(?:compose\s+)?exec\s+\S+\s+)*"
)
VERIFICATION_COMMAND = re.compile(
    COMMAND_BOUNDARY + COMMAND_PREFIX + r"(?:"
    r"(?:python(?:3)?\s+-m\s+)?(?:pytest|unittest|tox|nox|vitest|jest|ctest|phpunit|rspec)\b"
    r"|mix\s+test\b"
    r"|(?:cargo|go|npm|pnpm|yarn|bun|make|gradle|\./gradlew|gradlew|mvn|dotnet|bazel|just)"
    r"\b[^\n;&|]*\b(?:test|check|lint|build|fmt|clippy|typecheck|type-check|nextest|vet|ci|smoke|eval|evaluate|benchmark|bench)\b"
    r"|(?:ruff|eslint|pylint|mypy|pyright|tsc|flake8|shellcheck)\b"
    r"|gofmt\b[^\n;&|]*\s-l\b|(?:rustfmt|prettier)\b[^\n;&|]*--check\b"
    r"|biome\b[^\n;&|]*\bcheck\b|cmake\b[^\n;&|]*--build\b|ninja\b"
    r"|meson\s+(?:compile|test)\b|(?:diff|cmp)\b|grep\s+-q\b|jq\s+-e\b"
    r"|curl\b(?=[^\n;&|]*(?:\s-[A-Za-z]*f[A-Za-z]*\b|--fail(?:-with-body)?\b))"
    r"|wget\b(?=[^\n;&|]*--spider\b)|git\s+diff\s+--check\b)",
    re.I,
)
EXPLORATION_COMMAND = re.compile(
    COMMAND_BOUNDARY + COMMAND_PREFIX
    + r"(?:cat|find|grep|rg|ls|tree|head|tail|wc|pwd|stat|file|which|whereis|"
    r"sed\s+-n|git\s+(?:status|diff|show|log|grep|branch|rev-parse))\b",
    re.I,
)
EDIT_COMMAND = re.compile(
    COMMAND_BOUNDARY + COMMAND_PREFIX
    + r"(?:sed\s+-i|perl\s+-pi|git\s+apply\b|patch\s+-p\d*\b|"
    r"(?:cp|mv|rm|mkdir|touch|truncate)\b)",
    re.I,
)
SHELL_SEPARATORS = {";", "&", "&&", "|", "||", "(", ")"}
OUTPUT_REDIRECTS = {">", ">>", "&>", "&>>"}
DESCRIPTOR_REDIRECTS = {">&", ">>&"}
EXIT_CODE_RE = re.compile(r"(?:process\s+)?exit(?:ed)?(?:\s+with)?\s+(?:code\s*)?(-?\d+)", re.I)
FAILED_VALIDATION_OUTPUT_RE = re.compile(
    r"(?:^|\n)(?:FAILED|FAIL)\b|\b[1-9][0-9]*\s+failed\b|Failed Tests?\b|"
    r"AssertionError|--- FAIL:|Test Files\s+[1-9][0-9]*\s+failed|\berror\s+TS[0-9]+\b|"
    r"\berror\[E[0-9]+\]|Found\s+[1-9][0-9]*\s+errors?\b|Oh no!.*would reformat|"
    r"\[build failed\]",
    re.I,
)

def nested(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def canonical_tool(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    aliases = {
        "execcommandtool": "execcommand",
        "writefile": "write",
        "readfile": "read",
    }
    return aliases.get(normalized, normalized or "unknown")


def command_from(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("command", "cmd", "script"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return "\n".join(value)
    return ""


def target_from(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("file_path", "filePath", "path", "target", "filename"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def fingerprint(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


def shell_tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def is_real_output_target(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(
        normalized
        and normalized != "-"
        and not normalized.startswith("/dev/")
        and not normalized.startswith("/proc/")
    )


def has_real_file_output(command: str) -> bool:
    tokens = shell_tokens(command)
    if tokens is None:
        return False
    for index, token in enumerate(tokens):
        if token in OUTPUT_REDIRECTS and index + 1 < len(tokens):
            if is_real_output_target(tokens[index + 1]):
                return True
        if token in DESCRIPTOR_REDIRECTS:
            continue
        if token.rsplit("/", 1)[-1] != "tee":
            continue
        skip_next = False
        for argument in tokens[index + 1 :]:
            if argument in SHELL_SEPARATORS:
                break
            if skip_next:
                skip_next = False
                continue
            if argument == "--output-error":
                skip_next = True
                continue
            if argument.startswith("-"):
                continue
            if is_real_output_target(argument):
                return True
    return False


def operation_tags(
    name: str,
    arguments: Any,
    validation_kind: Any = None,
    validation_classification: Any = None,
) -> list[str]:
    tool = canonical_tool(name)
    if tool in NON_CLASSIFIED_TOOLS:
        return []
    command = command_from(arguments)
    tags: set[str] = set()
    if tool in DIRECT_EXPLORATION_TOOLS or any(
        token in tool for token in ("read", "grep", "search", "glob")
    ):
        tags.add("exploration")
    if tool in DIRECT_EDIT_TOOLS or any(
        token in tool for token in ("edit", "write", "patch", "replace")
    ):
        tags.add("editing")
    if tool in DIRECT_VERIFICATION_TOOLS or any(
        token in tool for token in ("test", "verify", "lint")
    ):
        tags.add("verification")
    if tool in EXECUTE_TOOLS or any(
        token in tool for token in ("shell", "exec", "terminal", "bash")
    ):
        if VERIFICATION_COMMAND.search(command):
            tags.add("verification")
        if EXPLORATION_COMMAND.search(command):
            tags.add("exploration")
        if EDIT_COMMAND.search(command) or has_real_file_output(command):
            tags.add("editing")
    if validation_classification == "validation" or validation_kind in {"test", "build", "lint"}:
        tags.add("verification")
    return sorted(tags)


def load_json_bytes(value: bytes, default: Any = None) -> Any:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return default


def load_json_path(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def file_record(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError:
        return {"path": str(path), "exists": False, "bytes": None, "sha256": None, "hash_status": "missing"}
    if size > HASH_LIMIT:
        return {"path": str(path.resolve()), "exists": True, "bytes": size, "sha256": None, "hash_status": "skipped_over_limit"}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "exists": True, "bytes": size, "sha256": digest.hexdigest(), "hash_status": "complete"}


def actor_fields(metadata: dict[str, Any], *, default_role: str = "main") -> dict[str, Any]:
    parent = metadata.get("parentSessionId") or metadata.get("parent_session_id")
    session_kind = metadata.get("sessionKind") or metadata.get("session_kind")
    role = "subagent" if parent or str(session_kind or "").lower() in {"subagent", "worker", "delegate"} else default_role
    return {
        "actor_role": role,
        "session_kind": session_kind,
        "agent_type": metadata.get("agentType") or metadata.get("agent_type") or metadata.get("type"),
        "session_name": metadata.get("sessionName") or metadata.get("session_name") or metadata.get("name"),
    }


def opencode_exit_code(state: dict[str, Any]) -> int | None:
    metadata = state.get("metadata")
    if isinstance(metadata, dict):
        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict):
            metadata = nested_metadata
        value = metadata.get("exit")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    output = state.get("output")
    if isinstance(output, dict):
        for key in ("exit", "exit_code", "exitCode"):
            value = output.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def result_status(call: dict[str, Any]) -> str:
    if call.get("is_error") is True:
        return "failure"
    status = str(call.get("status") or "").lower()
    if status in {"error", "failed", "failure", "cancelled", "timeout"}:
        return "failure"
    output = str(call.get("_output") or "")
    match = EXIT_CODE_RE.search(output)
    if match:
        return "success" if int(match.group(1)) == 0 else "failure"
    if "verification" in operation_tags(
        call.get("tool_name") or "", call.get("_arguments"), call.get("validation_kind"),
        call.get("validation_classification"),
    ):
        if FAILED_VALIDATION_OUTPUT_RE.search(output):
            return "failure"
    if status in {"completed", "success", "ok"}:
        return "success"
    return "unknown"


def usage_fields(values: Any) -> dict[str, int | float | None]:
    values = values if isinstance(values, dict) else {}
    aliases = {
        "input_tokens": ("input", "promptTokenCount", "input_tokens"),
        "output_tokens": ("output", "candidatesTokenCount", "output_tokens"),
        "reasoning_tokens": ("reasoning", "reasoningTokenCount", "reasoning_tokens"),
        "cache_read_tokens": ("cache_read", "cachedContentTokenCount", "cache_read_tokens"),
        "cache_write_tokens": ("cache_write", "cacheCreationTokenCount", "cache_write_tokens"),
    }
    cache = values.get("cache") if isinstance(values.get("cache"), dict) else {}
    output: dict[str, int | float | None] = {}
    for field, keys in aliases.items():
        candidates = [values.get(key) for key in keys]
        if field == "cache_read_tokens":
            candidates.append(cache.get("read"))
        if field == "cache_write_tokens":
            candidates.append(cache.get("write"))
        value = next((item for item in candidates if isinstance(item, (int, float)) and not isinstance(item, bool)), None)
        output[field] = value
    return output


def make_call(
    name: Any,
    arguments: Any,
    *,
    output: Any = "",
    status: Any = None,
    is_error: Any = None,
    tool_id: Any = None,
) -> dict[str, Any]:
    return {
        "raw_tool_name": str(name or "unknown"),
        "tool_name": canonical_tool(str(name or "")),
        "_arguments": arguments if isinstance(arguments, dict) else {},
        "_output": str(output or ""),
        "status": status,
        "is_error": is_error,
        "tool_id": str(tool_id) if tool_id else None,
        "validation_kind": None,
        "validation_classification": None,
    }


def round_key(request: dict[str, Any]) -> str:
    return "/".join((
        str(request.get("trial_key")),
        str(request.get("session_id")),
        f"{int(request.get('round_index') or 0):06d}",
    ))


def finalize_records(rounds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public_rounds: list[dict[str, Any]] = []
    public_calls: list[dict[str, Any]] = []
    for request in rounds:
        calls = request.pop("_calls", [])
        key = round_key(request)
        tag_counts = Counter(
            tag
            for call in calls
            for tag in operation_tags(
                call["tool_name"], call["_arguments"], call.get("validation_kind"),
                call.get("validation_classification"),
            )
        )
        statuses = Counter(result_status(call) for call in calls)
        public_rounds.append({
            **request,
            "methodology_version": METHODOLOGY_VERSION,
            "schema_version": SCHEMA_VERSION,
            "rule_version": RULE_VERSION,
            "round_key": key,
            "tool_call_count": len(calls),
            "tool_names": [call["tool_name"] for call in calls],
            "operation_tag_counts": dict(sorted(tag_counts.items())),
            "tool_result_status_counts": dict(sorted(statuses.items())),
        })
        for index, call in enumerate(calls, 1):
            arguments = call["_arguments"]
            public_calls.append({
                "methodology_version": METHODOLOGY_VERSION,
                "schema_version": SCHEMA_VERSION,
                "rule_version": RULE_VERSION,
                "job": request.get("job"),
                "trial_key": request.get("trial_key"),
                "task_name": request.get("task_name"),
                "adapter": request.get("adapter"),
                "session_id": request.get("session_id"),
                "round_key": key,
                "round_index": request.get("round_index"),
                "round_id": request.get("round_id"),
                "call_index": index,
                "tool_call_key": f"{key}/{index:03d}",
                "tool_id": call.get("tool_id"),
                "raw_tool_name": call["raw_tool_name"],
                "tool_name": call["tool_name"],
                "operation_tags": operation_tags(
                    call["tool_name"], arguments, call.get("validation_kind"),
                    call.get("validation_classification"),
                ),
                "validation_kind": call.get("validation_kind"),
                "validation_classification": call.get("validation_classification"),
                "argument_keys": sorted(str(item) for item in arguments),
                "command_fingerprint": fingerprint(command_from(arguments)),
                "target_fingerprint": fingerprint(target_from(arguments)),
                "result_status": result_status(call),
                "source_kind": request.get("source_kind"),
                "source": request.get("source"),
            })
    return public_rounds, public_calls


def trajectory_rounds(
    trajectory: dict[str, Any],
    base: dict[str, Any],
    source: str,
    *,
    actor: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actor = actor or actor_fields({}, default_role="main")
    rounds_data = trajectory.get("rounds") if isinstance(trajectory.get("rounds"), list) else []
    steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), list) else []
    steps_by_round: dict[str, list[dict[str, Any]]] = defaultdict(list)
    synthetic_order: list[str] = []
    for index, step in enumerate(steps, 1):
        if str(step.get("source") or "").lower() != "agent":
            continue
        current_id = str(step.get("round_id") or f"synthetic-{index:06d}")
        if current_id not in steps_by_round:
            synthetic_order.append(current_id)
        steps_by_round[current_id].append(step)

    ordered: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in rounds_data:
        current_id = str(item.get("round_id") or f"round-{len(ordered) + 1:06d}")
        ordered.append((current_id, item))
        seen.add(current_id)
    ordered.extend((current_id, {}) for current_id in synthetic_order if current_id not in seen)

    output = []
    for index, (current_id, round_data) in enumerate(ordered, 1):
        calls = []
        for step in steps_by_round.get(current_id, []):
            observation = step.get("observation")
            if isinstance(observation, (dict, list)):
                observation = json.dumps(observation, ensure_ascii=False, sort_keys=True)
            for call in step.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                calls.append(make_call(
                    call.get("function_name") or call.get("tool_name") or call.get("name"),
                    call.get("arguments"),
                    output=observation,
                    status=step.get("tool_status"),
                    is_error=call.get("is_error"),
                    tool_id=call.get("tool_id") or call.get("id"),
                ))
        output.append({
            **base,
            **actor,
            "session_id": str(round_data.get("session_id") or "main"),
            "round_index": index,
            "round_id": current_id,
            "source_kind": "trajectory",
            "source": source,
            **usage_fields(round_data.get("usage")),
            "_calls": calls,
        })

    subagents = trajectory.get("subagent_trajectories")
    if isinstance(subagents, dict):
        subagents = list(subagents.values())
    if isinstance(subagents, list):
        for sub_index, item in enumerate(subagents, 1):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else item
            nested_trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else item
            nested_rounds = trajectory_rounds(
                nested_trajectory,
                base,
                f"{source}#subagent-{sub_index}",
                actor=actor_fields(metadata, default_role="subagent"),
            )
            for request in nested_rounds:
                if request.get("session_id") == "main":
                    request["session_id"] = str(metadata.get("sessionId") or metadata.get("session_id") or f"subagent-{sub_index}")
            output.extend(nested_rounds)
    return output


def native_bitfun_rounds(
    bundle: zipfile.ZipFile, base: dict[str, Any], source: str
) -> tuple[list[dict[str, Any]], list[str]]:
    name = "agent/trajectory.bitfun.jsonl"
    completed: dict[str, list[str]] = defaultdict(list)
    round_data: dict[tuple[str, str], dict[str, Any]] = {}
    calls: dict[tuple[str, str], dict[str, Any]] = {}
    invalid = 0
    with bundle.open(name) as handle:
        for line_number, raw_line in enumerate(handle, 1):
            try:
                envelope = json.loads(raw_line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                invalid += 1
                continue
            event = envelope.get("event") if isinstance(envelope.get("event"), dict) else {}
            event_type = event.get("type")
            session_id = str(event.get("session_id") or "root")
            round_id = event.get("round_id")
            round_id = str(round_id) if isinstance(round_id, str) else None
            if event_type == "ModelRoundCompleted" and round_id is not None:
                if round_id not in completed[session_id]:
                    completed[session_id].append(round_id)
                round_data[(session_id, round_id)] = {
                    "source": f"{source}!/{name}:{line_number}",
                    **usage_fields(event.get("usage") or event.get("model_usage")),
                }
            elif event_type == "ToolEvent":
                tool_event = event.get("tool_event") if isinstance(event.get("tool_event"), dict) else {}
                call_id = tool_event.get("tool_id")
                if not isinstance(call_id, str):
                    continue
                key = (session_id, call_id)
                existing = calls.get(key)
                arguments = tool_event.get("params")
                if not isinstance(arguments, dict):
                    arguments = existing.get("_arguments", {}) if existing else {}
                call = make_call(
                    tool_event.get("effective_tool_name")
                    or tool_event.get("tool_name")
                    or (existing.get("raw_tool_name") if existing else "unknown"),
                    arguments,
                    output=nested(tool_event, "result", default=""),
                    status=tool_event.get("event_type"),
                    is_error=tool_event.get("event_type") == "Failed",
                    tool_id=call_id,
                )
                call["_native_round_id"] = round_id or (existing.get("_native_round_id") if existing else None)
                if existing:
                    if not call["_output"]:
                        call["_output"] = existing.get("_output", "")
                    if call["status"] in {None, "EarlyDetected", "ParamsPartial", "Started"}:
                        call["status"] = existing.get("status")
                calls[key] = call
            elif event_type == "aeo.runtime.bitfun_native" and event.get("kind") == "tools":
                native = event.get("observation") if isinstance(event.get("observation"), dict) else {}
                call_id = native.get("callId") or native.get("call_id")
                native_session = str(native.get("sessionId") or native.get("session_id") or "root")
                if isinstance(call_id, str):
                    call = calls.get((native_session, call_id))
                    if call is not None:
                        call["validation_kind"] = native.get("validationKind") or native.get("validation_kind")
                        call["validation_classification"] = (
                            native.get("validationClassification")
                            or native.get("validation_classification")
                        )

    by_round: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (session_id, _), call in calls.items():
        native_round = call.get("_native_round_id")
        if isinstance(native_round, str) and native_round in completed.get(session_id, []):
            call.pop("_native_round_id", None)
            by_round[(session_id, native_round)].append(call)
    output = []
    for session_id in sorted(completed):
        for index, round_id in enumerate(completed[session_id], 1):
            data = round_data.get((session_id, round_id), {})
            output.append({
                **base,
                **actor_fields({}, default_role="main"),
                "session_id": session_id,
                "round_index": index,
                "round_id": round_id,
                "source_kind": "bitfun_native_trajectory",
                "source": data.get("source") or f"{source}!/{name}",
                **{field: data.get(field) for field in (
                    "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
                    "cache_write_tokens",
                )},
                "_calls": by_round.get((session_id, round_id), []),
            })
    warnings = [f"skipped malformed BitFun trajectory lines={invalid}"] if invalid else []
    return output, warnings


def native_opencode_rounds(
    bundle: zipfile.ZipFile, base: dict[str, Any], source: str
) -> tuple[list[dict[str, Any]], list[str]]:
    name = next(
        candidate for candidate in ("agent/trajectory.opencode-v2.jsonl", "agent/trajectory.opencode.jsonl")
        if candidate in bundle.namelist()
    )
    completed: dict[str, list[str]] = defaultdict(list)
    round_data: dict[tuple[str, str], dict[str, Any]] = {}
    calls: dict[tuple[str, str], dict[str, Any]] = {}
    invalid = 0
    with bundle.open(name) as handle:
        for line_number, raw_line in enumerate(handle, 1):
            try:
                event = json.loads(raw_line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                invalid += 1
                continue
            event_type = event.get("type")
            part = event.get("part") if isinstance(event.get("part"), dict) else {}
            session_id = str(event.get("sessionID") or part.get("sessionID") or "root")
            message_id = part.get("messageID")
            message_id = str(message_id) if isinstance(message_id, str) else None
            if event_type == "step_finish" and message_id is not None:
                tokens = part.get("tokens")
                usage = usage_fields(tokens)
                if any(value is not None for value in usage.values()):
                    if message_id not in completed[session_id]:
                        completed[session_id].append(message_id)
                    round_data[(session_id, message_id)] = {
                        "source": f"{source}!/{name}:{line_number}",
                        **usage,
                    }
            elif event_type == "tool_use":
                call_id = part.get("callID") or part.get("id")
                if not isinstance(call_id, str):
                    continue
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                exit_code = opencode_exit_code(state)
                call = make_call(
                    part.get("tool") or "unknown",
                    state.get("input"),
                    output=state.get("output") or state.get("error") or "",
                    status=state.get("status"),
                    is_error=(
                        str(state.get("status") or "").lower() in {"error", "failed"}
                        or (exit_code is not None and exit_code != 0)
                    ),
                    tool_id=call_id,
                )
                call["_native_round_id"] = message_id
                calls[(session_id, call_id)] = call
            elif event_type == "aeo.native.runtime.tool":
                native = event.get("tool") if isinstance(event.get("tool"), dict) else {}
                call_id = native.get("callId") or native.get("call_id")
                native_session = str(native.get("sessionId") or native.get("session_id") or "root")
                if isinstance(call_id, str):
                    call = calls.get((native_session, call_id))
                    if call is None:
                        call = make_call(
                            native.get("toolName") or native.get("tool_name") or "unknown", {},
                            tool_id=call_id,
                        )
                        calls[(native_session, call_id)] = call
                    call["validation_kind"] = native.get("validationKind") or native.get("validation_kind")
                    call["validation_classification"] = (
                        native.get("validationClassification")
                        or native.get("validation_classification")
                    )

    by_round: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (session_id, _), call in calls.items():
        native_round = call.get("_native_round_id")
        if isinstance(native_round, str) and native_round in completed.get(session_id, []):
            call.pop("_native_round_id", None)
            by_round[(session_id, native_round)].append(call)
    output = []
    for session_id in sorted(completed):
        for index, message_id in enumerate(completed[session_id], 1):
            data = round_data[(session_id, message_id)]
            output.append({
                **base,
                **actor_fields({}, default_role="main"),
                "session_id": session_id,
                "round_index": index,
                "round_id": message_id,
                "source_kind": "opencode_native_trajectory",
                "source": data["source"],
                **{field: data.get(field) for field in (
                    "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
                    "cache_write_tokens",
                )},
                "_calls": by_round.get((session_id, message_id), []),
            })
    warnings = [f"skipped malformed OpenCode trajectory lines={invalid}"] if invalid else []
    return output, warnings


def bitfun_rounds(bundle: zipfile.ZipFile, base: dict[str, Any], source: str) -> tuple[list[dict[str, Any]], list[str]]:
    metadata_by_session: dict[str, dict[str, Any]] = {}
    trace_by_session: dict[str, list[str]] = defaultdict(list)
    session_re = re.compile(r"/sessions/([^/]+)/request-traces/(request-\d+\.json)$")
    metadata_re = re.compile(r"/sessions/([^/]+)/metadata\.json$")
    for name in bundle.namelist():
        trace_match = session_re.search(name)
        if trace_match:
            trace_by_session[trace_match.group(1)].append(name)
            continue
        metadata_match = metadata_re.search(name)
        if metadata_match:
            value = load_json_bytes(bundle.read(name), {})
            metadata_by_session[metadata_match.group(1)] = value if isinstance(value, dict) else {}

    rounds: list[dict[str, Any]] = []
    warnings: list[str] = []
    for session_id in sorted(trace_by_session):
        actor = actor_fields(metadata_by_session.get(session_id, {}))
        pending: dict[str, dict[str, Any]] = {}
        for index, name in enumerate(sorted(trace_by_session[session_id]), 1):
            record = load_json_bytes(bundle.read(name), {})
            if not isinstance(record, dict):
                warnings.append(f"invalid request trace: {source}!/{name}")
                continue
            if pending:
                messages = nested(record, "request", "body", "messages", default=[])
                unresolved = set(pending)
                if isinstance(messages, list):
                    for message in reversed(messages):
                        if not unresolved:
                            break
                        if not isinstance(message, dict) or str(message.get("role") or "").lower() != "tool":
                            continue
                        tool_id = str(message.get("tool_call_id") or "")
                        if tool_id in unresolved:
                            pending[tool_id]["_output"] = str(message.get("content") or "")
                            unresolved.remove(tool_id)
                for tool_id in set(pending) - unresolved:
                    pending.pop(tool_id, None)

            response = record.get("response") if isinstance(record.get("response"), dict) else {}
            calls = []
            for raw_call in response.get("tool_calls") or []:
                if not isinstance(raw_call, dict):
                    continue
                call = make_call(
                    raw_call.get("tool_name") or raw_call.get("name"),
                    raw_call.get("arguments"),
                    status=response.get("kind"),
                    is_error=raw_call.get("is_error"),
                    tool_id=raw_call.get("tool_id") or raw_call.get("id"),
                )
                calls.append(call)
                if call["tool_id"]:
                    pending[call["tool_id"]] = call
            rounds.append({
                **base,
                **actor,
                "session_id": session_id,
                "round_index": index,
                "round_id": str(record.get("turn_id") or record.get("trace_id") or Path(name).stem),
                "source_kind": "bitfun_request_trace",
                "source": f"{source}!/{name}",
                **usage_fields(response.get("usage")),
                "_calls": calls,
            })
    if not rounds:
        warnings.append(f"no BitFun request traces found in {source}")
    return rounds, warnings


def opencode_rounds(bundle: zipfile.ZipFile, base: dict[str, Any], source: str) -> tuple[list[dict[str, Any]], list[str]]:
    names = [name for name in bundle.namelist() if name.endswith("opencode-v2.log")]
    if not names:
        return [], [f"no OpenCode event log found in {source}"]
    name = min(names, key=len)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    malformed = 0
    with bundle.open(name) as handle:
        for line_number, raw_line in enumerate(handle, 1):
            try:
                event = json.loads(raw_line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                malformed += 1
                continue
            part = event.get("part") if isinstance(event.get("part"), dict) else {}
            session_id = str(event.get("sessionID") or part.get("sessionID") or "main")
            message_id = str(part.get("messageID") or "")
            if not message_id:
                continue
            key = (session_id, message_id)
            event_type = str(event.get("type") or "")
            if event_type == "step_start" and key not in by_key:
                order.append(key)
                by_key[key] = {
                    **base,
                    **actor_fields({}, default_role="main"),
                    "session_id": session_id,
                    "round_index": len(order),
                    "round_id": message_id,
                    "source_kind": "opencode_event_log",
                    "source": f"{source}!/{name}:{line_number}",
                    **usage_fields({}),
                    "_calls": [],
                }
            if key not in by_key:
                continue
            request = by_key[key]
            if event_type == "tool_use":
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                exit_code = opencode_exit_code(state)
                request["_calls"].append(make_call(
                    part.get("tool") or part.get("name"),
                    state.get("input"),
                    output=state.get("output") or state.get("error") or "",
                    status=state.get("status"),
                    is_error=(
                        str(state.get("status") or "").lower() in {"error", "failed"}
                        or (exit_code is not None and exit_code != 0)
                    ),
                    tool_id=part.get("id") or part.get("partID"),
                ))
            elif event_type == "step_finish":
                request.update(usage_fields(part.get("tokens")))
    warnings = [f"skipped malformed OpenCode log lines={malformed}"] if malformed else []
    return [by_key[key] for key in order], warnings


def rounds_from_agent_bundle(bundle: zipfile.ZipFile, base: dict[str, Any], source: str) -> tuple[list[dict[str, Any]], list[str], str]:
    names = bundle.namelist()
    if "agent/trajectory.bitfun.jsonl" in names:
        rounds, warnings = native_bitfun_rounds(bundle, {**base, "adapter": "bitfun"}, source)
        return rounds, warnings, "bitfun"
    if any(name in names for name in ("agent/trajectory.opencode-v2.jsonl", "agent/trajectory.opencode.jsonl")):
        rounds, warnings = native_opencode_rounds(bundle, {**base, "adapter": "opencode"}, source)
        return rounds, warnings, "opencode"
    trajectories = [name for name in names if name.endswith("agent/trajectory.json") or name.endswith("/trajectory.json")]
    if trajectories:
        name = min(trajectories, key=len)
        trajectory = load_json_bytes(bundle.read(name), {})
        if isinstance(trajectory, dict):
            adapter = str(nested(trajectory, "agent", "name", default="harbor-generic") or "harbor-generic")
            return trajectory_rounds(trajectory, {**base, "adapter": adapter}, f"{source}!/{name}"), [], adapter
    if any("/request-traces/request-" in name for name in names):
        rounds, warnings = bitfun_rounds(bundle, {**base, "adapter": "bitfun"}, source)
        return rounds, warnings, "bitfun"
    if any(name.endswith("opencode-v2.log") for name in names):
        rounds, warnings = opencode_rounds(bundle, {**base, "adapter": "opencode"}, source)
        return rounds, warnings, "opencode"
    return [], [f"unsupported agent bundle: {source}"], "unknown"


def trial_identity(result: dict[str, Any], fallback: str, job: str) -> dict[str, Any]:
    trial = str(result.get("trial_name") or result.get("id") or fallback)
    return {
        "job": job,
        "trial": trial,
        "trial_key": f"{job}/{trial}",
        "task_name": str(result.get("task_name") or fallback),
        "task_checksum": result.get("task_checksum"),
    }


def analyze_trial_directory(root: Path, job: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    result = load_json_path(root / "result.json", {})
    result = result if isinstance(result, dict) else {}
    fallback = root.name if not root.name.startswith("repeat-") else root.parent.parent.name
    base = trial_identity(result, fallback, job)
    warnings: list[str] = []
    trajectory_path = root / "agent" / "trajectory.json"
    if trajectory_path.is_file():
        trajectory = load_json_path(trajectory_path, {})
        adapter = str(nested(trajectory, "agent", "name", default="harbor-generic") or "harbor-generic")
        rounds = trajectory_rounds(trajectory if isinstance(trajectory, dict) else {}, {**base, "adapter": adapter}, str(trajectory_path.resolve()))
    elif (root / "agent.zip").is_file():
        with zipfile.ZipFile(root / "agent.zip") as bundle:
            rounds, warnings, adapter = rounds_from_agent_bundle(bundle, base, str((root / "agent.zip").resolve()))
    else:
        rounds, adapter = [], "unknown"
        warnings.append(f"trajectory evidence absent: {root}")
    return {
        **base,
        "trial_root": str(root.resolve()),
        "adapter": adapter,
        "round_coverage": "complete" if rounds else "absent",
        "warnings": warnings,
    }, rounds, warnings


def directory_trial_roots(path: Path) -> list[Path]:
    if (path / "result.json").is_file() and ((path / "agent").exists() or (path / "agent.zip").is_file()):
        return [path]
    return sorted({
        item.parent for item in path.rglob("result.json")
        if (item.parent / "agent").exists() or (item.parent / "agent.zip").is_file()
    })


def zip_trial_prefixes(bundle: zipfile.ZipFile) -> list[str]:
    names = set(bundle.namelist())
    prefixes = []
    for name in names:
        if not name.endswith("result.json"):
            continue
        prefix = name[: -len("result.json")]
        if f"{prefix}agent.zip" in names or any(candidate.startswith(f"{prefix}agent/") for candidate in names):
            prefixes.append(prefix)
    return sorted(set(prefixes))


def analyze_zip_input(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    trials: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    warnings: list[str] = []
    job = re.sub(r"-case-logs$", "", path.stem)
    with zipfile.ZipFile(path) as outer:
        prefixes = zip_trial_prefixes(outer)
        if not prefixes:
            raise ValueError(f"no trial result/agent pairs found in zip: {path}")
        names = set(outer.namelist())
        for prefix in prefixes:
            result = load_json_bytes(outer.read(f"{prefix}result.json"), {})
            result = result if isinstance(result, dict) else {}
            parts = [part for part in prefix.rstrip("/").split("/") if part and not part.startswith("repeat-")]
            fallback = parts[-1] if parts else "unknown"
            base = trial_identity(result, fallback, job)
            trial_warnings: list[str] = []
            trajectory_name = f"{prefix}agent/trajectory.json"
            if trajectory_name in names:
                trajectory = load_json_bytes(outer.read(trajectory_name), {})
                adapter = str(nested(trajectory, "agent", "name", default="harbor-generic") or "harbor-generic")
                trial_rounds = trajectory_rounds(
                    trajectory if isinstance(trajectory, dict) else {},
                    {**base, "adapter": adapter},
                    f"{path.resolve()}!/{trajectory_name}",
                )
            else:
                member = f"{prefix}agent.zip"
                # Python 3.10's zipfile expects a concrete file object exposing
                # ``seekable``; SpooledTemporaryFile does not provide it there.
                with tempfile.TemporaryFile(mode="w+b") as temporary:
                    with outer.open(member) as source_handle:
                        shutil.copyfileobj(source_handle, temporary)
                    temporary.seek(0)
                    with zipfile.ZipFile(temporary) as agent_bundle:
                        trial_rounds, trial_warnings, adapter = rounds_from_agent_bundle(
                            agent_bundle, base, f"{path.resolve()}!/{member}"
                        )
            trials.append({
                **base,
                "trial_root": f"{path.resolve()}!/{prefix}",
                "adapter": adapter,
                "round_coverage": "complete" if trial_rounds else "absent",
                "warnings": trial_warnings,
            })
            rounds.extend(trial_rounds)
            warnings.extend(trial_warnings)
    return trials, rounds, warnings


def analyze_input(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if path.is_file() and zipfile.is_zipfile(path):
        return analyze_zip_input(path)
    if not path.is_dir():
        raise ValueError(f"input must be a directory or zip: {path}")
    roots = directory_trial_roots(path)
    if not roots:
        raise ValueError(f"no trial directories found under {path}")
    if len(roots) == 1 and roots[0] == path:
        job = path.parent.parent.parent.name if path.name.startswith("repeat-") and path.parent.parent.name == "cases" else path.parent.name
    else:
        job = path.name
    trials: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    warnings: list[str] = []
    for root in roots:
        trial, trial_rounds, trial_warnings = analyze_trial_directory(root, job)
        trials.append(trial)
        rounds.extend(trial_rounds)
        warnings.extend(trial_warnings)
    return trials, rounds, warnings


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })
    temporary.replace(path)


def output_inside_directory_input(output: Path, inputs: Sequence[Path]) -> bool:
    return any(path.is_dir() and (output == path or path in output.parents) for path in inputs)


def run(args: argparse.Namespace) -> dict[str, Any]:
    inputs = [path.resolve() for path in args.inputs]
    output = args.output.resolve()
    output_level = getattr(args, "output_level", "compact")
    if output_inside_directory_input(output, inputs):
        raise ValueError("output directory must not be inside a directory input")
    trials: list[dict[str, Any]] = []
    internal_rounds: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in inputs:
        input_trials, input_rounds, input_warnings = analyze_input(path)
        trials.extend(input_trials)
        internal_rounds.extend(input_rounds)
        warnings.extend(input_warnings)
    rounds, calls = finalize_records(internal_rounds)

    output.mkdir(parents=True, exist_ok=True)
    by_job = {}
    for job in sorted({str(trial.get("job")) for trial in trials}):
        job_trials = [trial for trial in trials if trial.get("job") == job]
        job_rounds = [request for request in rounds if request.get("job") == job]
        job_calls = [call for call in calls if call.get("job") == job]
        by_job[job] = {
            "trials": len(job_trials),
            "rounds": len(job_rounds),
            "tool_calls": len(job_calls),
            "adapters": dict(sorted(Counter(str(trial.get("adapter")) for trial in job_trials).items())),
            "actor_roles": dict(sorted(Counter(str(request.get("actor_role")) for request in job_rounds).items())),
            "operation_tags": dict(sorted(Counter(tag for call in job_calls for tag in call["operation_tags"]).items())),
            "result_statuses": dict(sorted(Counter(str(call.get("result_status")) for call in job_calls).items())),
        }
    manifest = {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "rule_version": RULE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [file_record(path) if path.is_file() else {"path": str(path), "type": "directory"} for path in inputs],
        "output": str(output),
        "trial_count": len(trials),
        "round_count": len(rounds),
        "tool_call_count": len(calls),
        "output_level": output_level,
        "warnings": sorted(set(warnings)),
        "privacy": "prompt, reasoning, commands, arguments, and observations are not copied; command and target values use short SHA-256 fingerprints",
        "scope": "schema normalization only; operation tags are deterministic candidates, not behavior or root-cause findings",
    }
    summary_payload = {
        "jobs": by_job,
        **{
            key: manifest[key]
            for key in ("methodology_version", "schema_version", "trial_count", "round_count", "tool_call_count")
        },
    }
    write_json(output / "summary.json", summary_payload)
    if output_level == "compact":
        packed_rows = [{"record_type": "manifest", "data": manifest}]
        packed_rows.extend({"record_type": "trial", **row} for row in trials)
        packed_rows.extend({"record_type": "round", **row} for row in rounds)
        packed_rows.extend({"record_type": "tool_call", **row} for row in calls)
        write_jsonl(output / "trajectory-events.jsonl", packed_rows)
    else:
        write_json(output / "manifest.json", manifest)
        write_jsonl(output / "trials.jsonl", trials)
        write_jsonl(output / "rounds.jsonl", rounds)
        write_jsonl(output / "tool-calls.jsonl", calls)
        write_csv(output / "trials.csv", trials, list(trials[0].keys()) if trials else ["trial_key"])
        write_csv(output / "rounds.csv", rounds, list(rounds[0].keys()) if rounds else ["round_key"])
        write_csv(output / "tool-calls.csv", calls, list(calls[0].keys()) if calls else ["tool_call_key"])
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "output": str(output),
        "trials": len(trials),
        "rounds": len(rounds),
        "tool_calls": len(calls),
        "warnings": len(set(warnings)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, metavar="INPUT")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-level", choices=("compact", "full"), default="compact")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
