#!/usr/bin/env python3
"""Extract reproducible, redacted evidence from Harbor-style agent trajectories."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_VERSION = "1.1.0"
SCHEMA_VERSION = 1
METHODOLOGY_VERSION = "2.2.0"
RULE_VERSION = "trajectory-audit-v2"
BOOTSTRAP_SEED = 20260918
BOOTSTRAP_SAMPLES = 10_000
HASH_LIMIT = 64 * 1024 * 1024

VALIDATION_RE = re.compile(
    r"(?:^|[;&| ]|\./)(?:mvnw?|gradlew?|pytest|python\s+-m\s+pytest|go\s+test|"
    r"cargo\s+(?:test|check|clippy)|npm\s+(?:test|run\s+(?:test|lint|build|typecheck))|"
    r"pnpm\s+(?:test|run\s+(?:test|lint|build|typecheck))|yarn\s+(?:test|lint|build)|"
    r"make\s+(?:test|check)|ctest|tsc)(?:\s|$)",
    re.I,
)
SHELL_MUTATION_RE = re.compile(
    r"(?:apply_patch|sed\s+-i|perl\s+-pi|git\s+apply|(?:^|\s)(?:cp|mv)\s+)", re.I
)
NETWORK_ACCESS_RE = re.compile(
    r"(?:\bcurl\b|\bwget\b|\bgit\s+(?:clone|fetch|pull|ls-remote)\b|"
    r"\bgh\s+(?:api|issue|pr)\b|\bwebfetch\b)",
    re.I,
)
DEPENDENCY_FETCH_RE = re.compile(
    r"\b(?:npm|pnpm|yarn|pip|pip3|uv|cargo|go)\s+(?:install|add|update|get|sync|fetch)\b",
    re.I,
)
EVALUATION_MUTATION_RE = re.compile(
    r"(?:^|[/\\])(?:verifier|hidden[-_]?tests?)(?:[/\\]|$)|"
    r"(?:reward|result)\.json\b|(?:artifacts[/\\]model|fix)\.patch\b",
    re.I,
)
TEST_PATH_RE = re.compile(r"(?:^|[/\\])(?:tests?|specs?|__tests__)(?:[/\\]|$)|(?:test|spec)\.[A-Za-z0-9]+$", re.I)
ERROR_RE = re.compile(
    r"(?:\berror\b|\bfail(?:ed|ure)?\b|exception|traceback|timed?\s*out|"
    r"exit(?:ed)?\s+(?:with\s+)?(?:code\s*)?[1-9]\d*|command failed|not found|denied)",
    re.I,
)
INFRA_RE = re.compile(
    r"(?:provider|rate.?limit|worker|container|docker|network|dns|connection|disk|"
    r"no space|quota|mount|image pull|service unavailable|gateway|timeout|timed out|cancelled)",
    re.I,
)
INFRA_ERROR_RE = re.compile(
    r"(?:timed?\s*out|timeout:\s*(?:failed|error)|connection\s+(?:refused|reset|timed out)|"
    r"could not resolve|network is unreachable|proxyconnect\b|(?:http\s*)?(?:403|429|502|503)\s+(?:forbidden|error|bad gateway|service unavailable)|"
    r"rate.?limit(?:ed| exceeded)?|no space left|disk quota|image pull (?:failed|error)|"
    r"docker:\s*(?:error|failed)|container.{0,80}(?:failed|error)|mount.{0,80}(?:failed|denied|error)|"
    r"provider.{0,80}(?:failed|unavailable|rate.?limit|timed?\s*out)|worker.{0,80}(?:lost|failed|unavailable)|"
    r"(?:operation|request|job)\s+cancelled)",
    re.I,
)
FINAL_CLAIM_RE = re.compile(
    r"(?:all|full|entire).{0,40}(?:tests?|suite).{0,30}(?:pass|success)|"
    r"(?:tests?|suite).{0,30}(?:all\s+pass|0\s+fail|success)",
    re.I | re.S,
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|cookie|access[_-]?token|refresh[_-]?token|"
    r"token|secret|password|passwd)\b(\s*[:=]\s*)([^\s,;\]\}\"']+|\"[^\"]*\"|'[^']*')"
)
ENV_SECRET_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|COOKIE|AUTHORIZATION))"
    r"(\s*=\s*)([^\s,;\]\}\"']+|\"[^\"]*\"|'[^']*')"
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def nested(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def first_value(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(start: Any, finish: Any) -> float | None:
    left, right = parse_time(start), parse_time(finish)
    if not left or not right:
        return None
    return round((right - left).total_seconds(), 6)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "bytes": None, "sha256": None, "hash_status": "missing"}
    size = path.stat().st_size
    return {
        "path": str(path.resolve()),
        "exists": True,
        "bytes": size,
        "sha256": sha256(path) if size <= HASH_LIMIT else None,
        "hash_status": "complete" if size <= HASH_LIMIT else "skipped_over_64_mib",
    }


def stable_hash(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def redact_text(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = BEARER_RE.sub("Bearer <redacted>", text)
    text = SK_RE.sub("sk-<redacted>", text)
    text = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", text)
    text = ENV_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def provenance(path: Path | None, field: str, adapter: str, status: str, confidence: str = "direct") -> dict[str, Any]:
    return {
        "source_path": str(path.resolve()) if path and path.exists() else (str(path) if path else None),
        "source_field": field,
        "adapter": adapter,
        "status": status,
        "confidence": confidence,
    }


def observation_text(step: dict[str, Any]) -> str:
    observation = step.get("observation")
    if isinstance(observation, str):
        return observation
    if isinstance(observation, dict):
        results = observation.get("results")
        if isinstance(results, list):
            return "\n".join(
                str(item.get("content", "")) for item in results if isinstance(item, dict)
            )
        return json.dumps(observation, ensure_ascii=False, sort_keys=True)
    return ""


def ctrf_tests(data: Any) -> list[dict[str, Any]]:
    for candidate in (
        nested(data, "results", "tests"),
        nested(data, "testResults"),
        nested(data, "tests"),
    ):
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def test_fingerprint(tests: Sequence[dict[str, Any]]) -> str | None:
    identities = []
    for test in tests:
        name = str(test.get("name") or test.get("test") or "").strip()
        suite = str(test.get("suite") or test.get("filepath") or test.get("file") or "").strip()
        if name or suite:
            identities.append((suite, name))
    if not identities:
        return None
    payload = json.dumps(sorted(set(identities)), ensure_ascii=False, separators=(",", ":"))
    return stable_hash(payload)


def patch_stats(path: Path | None) -> dict[str, int | None]:
    if not path or not path.is_file():
        return {"files": None, "additions": None, "deletions": None}
    files = additions = deletions = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("diff --git "):
            files += 1
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {"files": files, "additions": additions, "deletions": deletions}


def read_first_line(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    return value or None


def detect_adapter(root: Path, config: dict[str, Any], trajectory: dict[str, Any]) -> str:
    agent_name = str(
        first_value(
            nested(trajectory, "agent", "name"),
            nested(config, "agent", "name"),
            "",
        )
    ).lower()
    if (root / "agent" / "bitfun").exists() or "bitfun" in agent_name:
        return "bitfun"
    if "opencode" in agent_name:
        return "opencode"
    return "harbor-generic"


def choose_patch(root: Path) -> dict[str, Any]:
    paths = [
        root / "artifacts" / "model.patch",
        root / "agent" / "model.patch",
        root / "agent" / "patch" / "fix.patch",
    ]
    records = [file_record(path) for path in paths if path.is_file()]
    nonempty = [path for path in paths if path.is_file() and path.stat().st_size > 0]
    chosen = nonempty[0] if nonempty else next((path for path in paths if path.is_file()), None)
    nonempty_hashes = {record["sha256"] for record in records if record["bytes"] and record["sha256"]}
    return {
        "path": str(chosen.resolve()) if chosen else None,
        "bytes": chosen.stat().st_size if chosen else None,
        "sha256": sha256(chosen) if chosen and chosen.stat().st_size <= HASH_LIMIT else None,
        "stats": patch_stats(chosen),
        "candidates": records,
        "contradictory": len(nonempty_hashes) > 1,
    }


def final_stream_model_usage(root: Path) -> tuple[dict[str, Any] | None, Path | None, int]:
    candidates = [
        root / "agent" / "codeagent-stream.jsonl",
        root / "agent" / "raw-stream.jsonl",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        results: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict) and item.get("type") == "result":
                        results.append(item)
        except OSError:
            continue
        if results:
            usage = results[-1].get("modelUsage")
            if isinstance(usage, dict) and usage:
                return usage, path, len(results)
    return None, None, 0


def extract_tokens(root: Path, result: dict[str, Any], trajectory: dict[str, Any], adapter: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    prov: dict[str, Any] = {}
    agent_result = result.get("agent_result") if isinstance(result.get("agent_result"), dict) else {}
    final_metrics = trajectory.get("final_metrics") if isinstance(trajectory.get("final_metrics"), dict) else {}
    model_usage, stream_path, stream_segments = final_stream_model_usage(root)

    stream_values: dict[str, int | float | None] = {}
    if model_usage:
        entries = [item for item in model_usage.values() if isinstance(item, dict)]
        stream_values = {
            "input_tokens": sum(number(item.get("inputTokens")) or 0 for item in entries),
            "output_tokens": sum(number(item.get("outputTokens")) or 0 for item in entries),
            "cache_read_tokens": sum(number(item.get("cacheReadInputTokens")) or 0 for item in entries),
            "cache_creation_tokens": sum(number(item.get("cacheCreationInputTokens")) or 0 for item in entries),
            "cost_usd": sum(number(item.get("costUSD")) or 0 for item in entries),
        }

    bitfun_stats_path = root / "agent" / "bitfun" / "token_usage" / "model_stats.json"
    bitfun_stats = load_json(bitfun_stats_path, {}) or {}
    stat_entries = [item for item in bitfun_stats.values() if isinstance(item, dict)] if isinstance(bitfun_stats, dict) else []
    bitfun_values = {
        "input_tokens": sum(number(item.get("total_input")) or 0 for item in stat_entries) if stat_entries else None,
        "output_tokens": sum(number(item.get("total_output")) or 0 for item in stat_entries) if stat_entries else None,
        "cache_read_tokens": sum(number(item.get("total_cached")) or 0 for item in stat_entries) if stat_entries else None,
        "cache_creation_tokens": sum(number(item.get("total_cache_write")) or 0 for item in stat_entries) if stat_entries else None,
        "request_count": sum(number(item.get("request_count")) or 0 for item in stat_entries) if stat_entries else None,
        "session_count": sum(number(item.get("session_count")) or 0 for item in stat_entries) if stat_entries else None,
    }
    result_values = {
        "input_tokens": number(agent_result.get("n_input_tokens")),
        "output_tokens": number(agent_result.get("n_output_tokens")),
        "cache_read_tokens": number(agent_result.get("n_cache_tokens")),
        "cache_creation_tokens": number(agent_result.get("n_cache_creation_tokens")),
        "cost_usd": number(agent_result.get("cost_usd")),
    }
    trajectory_values = {
        "input_tokens": number(final_metrics.get("total_prompt_tokens")),
        "output_tokens": number(final_metrics.get("total_completion_tokens")),
        "cache_read_tokens": number(final_metrics.get("total_cached_tokens")),
        "cache_creation_tokens": number(final_metrics.get("total_cache_creation_tokens")),
    }

    if model_usage:
        primary, primary_path, primary_field = stream_values, stream_path, "last result.modelUsage"
    else:
        primary, primary_path, primary_field = result_values, root / "result.json", "agent_result"

    values: dict[str, Any] = {}
    for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "cost_usd"):
        value = first_value(primary.get(field), bitfun_values.get(field), trajectory_values.get(field))
        values[field] = value
        if primary.get(field) is not None:
            prov[field] = provenance(primary_path, f"{primary_field}.{field}", adapter, "complete")
        elif bitfun_values.get(field) is not None:
            prov[field] = provenance(bitfun_stats_path, field, adapter, "fallback", "corroborated")
        elif trajectory_values.get(field) is not None:
            prov[field] = provenance(root / "agent" / "trajectory.json", f"final_metrics.{field}", adapter, "fallback", "corroborated")
        else:
            prov[field] = provenance(None, field, adapter, "missing", "unknown")

    if values["input_tokens"] is not None and values["output_tokens"] is not None:
        values["total_tokens_excluding_cache"] = values["input_tokens"] + values["output_tokens"]
    else:
        values["total_tokens_excluding_cache"] = None
    values["request_count"] = bitfun_values.get("request_count")
    values["session_count"] = bitfun_values.get("session_count")
    values["stream_result_segments"] = stream_segments or None

    comparisons = [
        ("result", result_values),
        ("bitfun_stats", bitfun_values),
        ("trajectory", trajectory_values),
    ]
    for field in ("input_tokens", "output_tokens", "cache_read_tokens"):
        observed = {(name, source.get(field)) for name, source in comparisons if source.get(field) is not None}
        if len({value for _, value in observed}) > 1:
            warnings.append(f"{field} differs across ledgers: {sorted(observed)}")
    return values, prov, warnings


def reward_dict(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    candidate = data.get("rewards") if isinstance(data.get("rewards"), dict) else data
    return candidate if isinstance(candidate, dict) and any(key in candidate for key in ("reward", "partial", "f2p_total", "p2p_total")) else None


def normalized_reward(values: dict[str, Any] | None) -> dict[str, Any]:
    values = values or {}
    normalized = {
        key: number(values.get(key))
        for key in (
            "reward", "partial", "f2p", "f2p_total", "f2p_passed", "p2p", "p2p_total", "p2p_passed",
            "n2p", "n2p_total", "n2p_passed", "s2p", "s2p_total", "s2p_passed",
        )
    }
    for prefix in ("f2p", "p2p", "n2p", "s2p"):
        total, passed = normalized.get(f"{prefix}_total"), normalized.get(f"{prefix}_passed")
        normalized[f"{prefix}_failed"] = total - passed if total is not None and passed is not None else None
    return normalized


def phase_durations(result: dict[str, Any]) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for key in ("environment_setup", "agent_setup", "agent_execution", "verifier"):
        item = result.get(key)
        output[key] = seconds_between(item.get("started_at"), item.get("finished_at")) if isinstance(item, dict) else None
    return output


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip())


def tool_events(steps: Sequence[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for index, step in enumerate(steps, start=1):
        step_id = step.get("step_id") if step.get("step_id") is not None else index
        observation = observation_text(step)
        for call in step.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            command = str(first_value(arguments.get("command"), arguments.get("cmd"), ""))
            file_path = str(first_value(arguments.get("file_path"), arguments.get("filePath"), arguments.get("path"), ""))
            yield {
                "step_id": step_id,
                "timestamp": step.get("timestamp"),
                "function_name": str(first_value(call.get("function_name"), call.get("name"), "")),
                "arguments": arguments,
                "command": command,
                "file_path": file_path,
                "observation": observation,
            }


def is_mutation(event: dict[str, Any]) -> bool:
    name = event["function_name"].lower().replace("_", "")
    if name in {"write", "edit", "multiedit", "applypatch", "createfile", "writefile"}:
        return "<tool_use_error>" not in event["observation"]
    return bool(event["command"] and SHELL_MUTATION_RE.search(event["command"]))


def mutation_target(event: dict[str, Any]) -> str:
    return event["file_path"] or event["command"]


def access_result(observation: str) -> str:
    if not observation:
        return "unknown"
    return "failure" if ERROR_RE.search(observation) else "success"


def make_candidate(trial_key: str, focus: str, candidate_type: str, summary: str, evidence_paths: Sequence[str], step_id: Any = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "trial_key": trial_key,
        "focus": focus,
        "candidate_type": candidate_type,
        "status": "heuristic",
        "step_id": step_id,
        "evidence_paths": list(evidence_paths),
        "summary": redact_text(summary),
        "details": details or {},
        "rule_version": RULE_VERSION,
    }


def test_target(value: str) -> str:
    matches = re.findall(
        r"(?:[A-Za-z0-9_.-]+[/\\])*(?:[A-Za-z0-9_.-]*(?:test|spec)[A-Za-z0-9_.-]*)\.[A-Za-z0-9]+",
        value,
        re.I,
    )
    return matches[0] if matches else redact_text(value, 180)


def dedupe_candidates(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        candidate_type = row["candidate_type"]
        if candidate_type == "environment_error_candidate":
            key = (row["trial_key"], candidate_type, nested(row, "details", "signal"))
        elif candidate_type in {"public_test_modification_candidate", "evaluation_artifact_mutation_candidate"}:
            key = (row["trial_key"], candidate_type, nested(row, "details", "target"))
        else:
            key = (row["trial_key"], candidate_type, row.get("step_id"), row["summary"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def extract_trial(root: Path, job_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = root.resolve()
    job_root = job_root.resolve()
    result_path = root / "result.json"
    config_path = root / "config.json"
    trajectory_path = root / "agent" / "trajectory.json"
    reward_path = root / "verifier" / "reward.json"
    ctrf_path = root / "verifier" / "ctrf.json"
    result = load_json(result_path, {}) or {}
    config = load_json(config_path, {}) or {}
    trajectory = load_json(trajectory_path, {}) or {}
    ctrf = load_json(ctrf_path, {}) or {}
    adapter = detect_adapter(root, config, trajectory)
    job_alias = job_root.name
    trial_name = str(first_value(result.get("trial_name"), root.name))
    trial_key = f"{job_alias}/{trial_name}"
    candidates: list[dict[str, Any]] = []

    steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), list) else []
    events = list(tool_events(steps))
    mutation_events = [event for event in events if is_mutation(event)]
    validation_events = [event for event in events if event["command"] and VALIDATION_RE.search(event["command"])]
    mutation_ids = [int(event["step_id"]) for event in mutation_events if str(event["step_id"]).isdigit()]
    last_mutation = max(mutation_ids, default=None)
    validation_after_last = (
        any(int(event["step_id"]) > last_mutation for event in validation_events if str(event["step_id"]).isdigit())
        if last_mutation is not None else bool(validation_events)
    )
    by_command: dict[str, list[int]] = defaultdict(list)
    for event in validation_events:
        if str(event["step_id"]).isdigit():
            by_command[normalize_command(event["command"])].append(int(event["step_id"]))
    repeated_validations = 0
    for step_ids in by_command.values():
        for previous, current in zip(step_ids, step_ids[1:]):
            if not any(previous < mutation < current for mutation in mutation_ids):
                repeated_validations += 1

    for event in events:
        command = event["command"]
        observation = event["observation"]
        function_name = event["function_name"].lower()
        native_url = ""
        if "webfetch" in function_name or function_name in {"browser", "fetch", "http"}:
            native_url = str(first_value(event["arguments"].get("url"), event["arguments"].get("uri"), ""))
        access_expression = command or native_url
        if access_expression and (NETWORK_ACCESS_RE.search(access_expression) or DEPENDENCY_FETCH_RE.search(access_expression) or native_url):
            candidate_type = "dependency_or_tool_fetch" if DEPENDENCY_FETCH_RE.search(access_expression) else "external_access_candidate"
            candidates.append(make_candidate(
                trial_key,
                "integrity",
                candidate_type,
                access_expression,
                [str(trajectory_path.resolve())],
                event["step_id"],
                {"access_result": access_result(observation)},
            ))
        if is_mutation(event):
            target = mutation_target(event)
            if EVALUATION_MUTATION_RE.search(target):
                candidates.append(make_candidate(
                    trial_key, "integrity", "evaluation_artifact_mutation_candidate", target,
                    [str(trajectory_path.resolve())], event["step_id"], {"target": test_target(target)}
                ))
            elif TEST_PATH_RE.search(target):
                target_key = test_target(target)
                candidates.append(make_candidate(
                    trial_key, "integrity", "public_test_modification_candidate", target_key,
                    [str(trajectory_path.resolve())], event["step_id"], {"target": target_key}
                ))
        infra_match = INFRA_ERROR_RE.search(observation) if command and observation else None
        if infra_match:
            candidates.append(make_candidate(
                trial_key, "environment", "environment_error_candidate", observation,
                [str(trajectory_path.resolve())], event["step_id"], {"signal": infra_match.group(0).lower()}
            ))

    agent_steps = [step for step in steps if str(step.get("source", "")).lower() == "agent"]
    final_agent_step = agent_steps[-1] if agent_steps else {}
    final_message = str(final_agent_step.get("message") or "")
    normal_final = bool(final_message.strip()) and not (final_agent_step.get("tool_calls") or [])

    patch = choose_patch(root)
    baseline_path = root / "agent" / "patch" / "git-baseline-commit.txt"
    baseline = first_value(read_first_line(baseline_path), nested(config, "task", "git_commit_id"))
    user_messages = [str(step.get("message") or "") for step in steps if str(step.get("source", "")).lower() == "user" and step.get("message")]
    prompt_fingerprint = stable_hash(user_messages[0]) if user_messages else None

    result_rewards = reward_dict(nested(result, "verifier_result", "rewards"))
    verifier_rewards = reward_dict(load_json(reward_path, None))
    raw_result_path = next((path for path in (root / "result.raw.json", root / "result.json.bak") if path.is_file()), None)
    raw_result = load_json(raw_result_path, {}) if raw_result_path else {}
    raw_rewards = reward_dict(nested(raw_result, "verifier_result", "rewards")) if raw_result else None
    raw_score = normalized_reward(first_value(raw_rewards, result_rewards))
    final_score = normalized_reward(first_value(verifier_rewards, result_rewards))
    score_differs = raw_score != final_score
    reconciliation_files = [
        path for path in (root / "reverify-applied.json", root / "reconciliation.json", job_root / "reconciliation.json") if path.is_file()
    ]
    reconciliation_documented = bool(reconciliation_files)

    tests = ctrf_tests(ctrf)
    verifier_fingerprint = test_fingerprint(tests)
    failed_tests = sum(
        str(item.get("status", "")).lower() not in {"passed", "pass", "success", "skipped"}
        for item in tests
    ) if tests else None

    tokens, token_prov, token_warnings = extract_tokens(root, result, trajectory, adapter)
    started_at, finished_at = result.get("started_at"), result.get("finished_at")
    duration = seconds_between(started_at, finished_at)
    phase_times = phase_durations(result)
    exception_info = result.get("exception_info") or result.get("exception")
    if isinstance(exception_info, dict):
        exception_type = str(first_value(exception_info.get("exception_type"), exception_info.get("type"), exception_info.get("message"), ""))
    else:
        exception_type = str(exception_info or "")
    stop_reason = str(nested(trajectory, "final_metrics", "extra", "stop_reason", default="") or "")
    censored = bool(re.search(r"timeout|timed out|cancel", f"{exception_type} {stop_reason}", re.I))

    step_timestamps = {int(step.get("step_id")): parse_time(step.get("timestamp")) for step in steps if str(step.get("step_id", "")).isdigit()}
    run_started = parse_time(started_at)
    first_mutation_time = step_timestamps.get(min(mutation_ids)) if mutation_ids else None
    time_to_first_mutation = round((first_mutation_time - run_started).total_seconds(), 6) if first_mutation_time and run_started else None
    validation_after = [event for event in validation_events if last_mutation is not None and str(event["step_id"]).isdigit() and int(event["step_id"]) > last_mutation]
    last_mutation_time = step_timestamps.get(last_mutation) if last_mutation is not None else None
    first_validation_time = step_timestamps.get(int(validation_after[0]["step_id"])) if validation_after else None
    mutation_to_validation = round((first_validation_time - last_mutation_time).total_seconds(), 6) if first_validation_time and last_mutation_time else None

    coverage: dict[str, str] = {}
    task_name = str(result.get("task_name") or "") or None
    task_checksum = str(result.get("task_checksum") or "") or None
    coverage["identity"] = "complete" if task_name and task_checksum else ("partial" if task_name else "absent")
    coverage["trace"] = "complete" if steps else "absent"
    coverage["delivery"] = "contradictory" if patch["contradictory"] else ("complete" if patch["path"] else "absent")
    if score_differs and not reconciliation_documented:
        coverage["verifier"] = "contradictory"
    elif final_score["reward"] is not None and tests:
        coverage["verifier"] = "complete"
    elif final_score["reward"] is not None:
        coverage["verifier"] = "partial"
    else:
        coverage["verifier"] = "absent"
    environment_type = nested(config, "environment", "type")
    coverage["environment"] = "complete" if environment_type and (root / "trial.log").is_file() else ("partial" if environment_type else "absent")
    raw_integrity = bool((root / "agent" / "bitfun" / "request-traces.tar.gz").is_file() or (root / "agent" / "bitfun" / "request-traces").exists())
    coverage["integrity"] = "complete" if steps and raw_integrity else ("partial" if steps else "absent")
    present_tokens = sum(tokens[field] is not None for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"))
    coverage["tokens"] = "complete" if present_tokens == 4 else ("partial" if present_tokens else "absent")
    present_phases = sum(value is not None for value in phase_times.values())
    coverage["latency"] = "complete" if duration is not None and present_phases >= 2 else ("partial" if duration is not None else "absent")

    if exception_type and INFRA_RE.search(exception_type) and not mutation_events and not patch["path"]:
        health = "infra_failed"
    elif coverage["verifier"] == "absent" and (mutation_events or patch["path"]):
        health = "behavior_unverified"
    elif any(value == "contradictory" for value in coverage.values()) or coverage["identity"] != "complete" or coverage["trace"] == "absent" or coverage["delivery"] == "absent":
        health = "degraded"
    else:
        health = "valid"

    reward = final_score["reward"]
    failed = reward is not None and reward <= 0
    if failed:
        candidates.append(make_candidate(trial_key, "score", "FM-01", "reconciled verifier reward <= 0", [str(reward_path if reward_path.is_file() else result_path)]))
    if exception_type:
        candidates.append(make_candidate(trial_key, "environment", "FM-02", f"exception={exception_type}", [str(result_path)]))
    if not normal_final:
        candidates.append(make_candidate(trial_key, "process", "FM-03", "no normal final no-tool message observed", [str(trajectory_path)]))
    if failed and normal_final:
        candidates.append(make_candidate(trial_key, "process", "FM-04", "normal final response but verifier failed", [str(trajectory_path), str(reward_path)]))
    if failed and not patch["path"]:
        candidates.append(make_candidate(trial_key, "process", "FM-05", "captured patch missing", [str(root / "artifacts"), str(root / "agent")]))
    elif failed and patch["bytes"] == 0:
        candidates.append(make_candidate(trial_key, "process", "FM-05", "captured patch empty", [str(patch["path"])]))
    if (final_score.get("f2p_failed") or 0) > 0:
        candidates.append(make_candidate(trial_key, "score", "FM-06", f"F2P failures={final_score['f2p_failed']}", [str(reward_path)]))
    if any((final_score.get(f"{prefix}_failed") or 0) > 0 for prefix in ("p2p", "n2p", "s2p")):
        candidates.append(make_candidate(trial_key, "score", "FM-07", "regression or transition failures observed", [str(reward_path), str(ctrf_path)]))
    if mutation_events and not validation_after_last:
        candidates.append(make_candidate(trial_key, "process", "FM-08", f"last mutation step={last_mutation}; no later recognized validation", [str(trajectory_path)], last_mutation))
    if failed and FINAL_CLAIM_RE.search(final_message):
        candidates.append(make_candidate(trial_key, "process", "FM-09", "final response claims broad validation but verifier failed", [str(trajectory_path), str(reward_path)]))
    if repeated_validations:
        candidates.append(make_candidate(trial_key, "process", "FM-10", f"equivalent validation repeats without mutation={repeated_validations}", [str(trajectory_path)]))
    if token_warnings or (tokens["input_tokens"] is None and tokens["output_tokens"] is None):
        candidates.append(make_candidate(trial_key, "tokens", "FM-12", "; ".join(token_warnings) or "token ledger absent", [str(result_path), str(trajectory_path)]))
    if score_differs:
        candidates.append(make_candidate(trial_key, "score", "FM-13", "raw/stored and final verifier reward differ", [str(result_path), str(reward_path)], details={"reconciliation_documented": reconciliation_documented}))
    test_total = first_value(final_score.get("f2p_total"), 0) + first_value(final_score.get("p2p_total"), 0)
    if failed and not tests and test_total == 0:
        candidates.append(make_candidate(trial_key, "score", "FM-14", "no tests captured in verifier evidence", [str(reward_path), str(ctrf_path)]))

    artifact_paths = [result_path, config_path, trajectory_path, reward_path, ctrf_path]
    if patch["path"]:
        artifact_paths.append(Path(patch["path"]))
    artifacts = {path.name if path.parent == root else str(path.relative_to(root)): file_record(path) for path in artifact_paths}

    agent_name = first_value(nested(trajectory, "agent", "name"), nested(config, "agent", "name"))
    agent_version = first_value(nested(trajectory, "agent", "version"), nested(result, "agent_result", "metadata", "version"))
    model_name = first_value(nested(trajectory, "agent", "model_name"), nested(config, "agent", "model_name"))
    tool_counts = Counter(event["function_name"] for event in events)
    record = {
        "trial_key": trial_key,
        "job": job_alias,
        "job_root": str(job_root.resolve()),
        "trial": trial_name,
        "trial_id": result.get("id"),
        "trial_root": str(root.resolve()),
        "task_name": task_name,
        "task_checksum": task_checksum,
        "baseline": baseline,
        "prompt_fingerprint": prompt_fingerprint,
        "verifier_fingerprint": verifier_fingerprint,
        "adapter": adapter,
        "agent": agent_name,
        "agent_version": agent_version,
        "model": model_name,
        "environment_type": environment_type,
        "health": health,
        "coverage": coverage,
        "score": {
            "raw": raw_score,
            "reconciled": final_score,
            "changed": score_differs,
            "reconciliation_documented": reconciliation_documented,
            "failed_tests_in_ctrf": failed_tests,
        },
        "tokens": tokens,
        "latency": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_sec": duration,
            "censored": censored,
            "phase_duration_sec": phase_times,
            "time_to_first_mutation_sec": time_to_first_mutation,
            "last_mutation_to_validation_sec": mutation_to_validation,
        },
        "process": {
            "steps": len(steps),
            "tool_calls": len(events),
            "tool_counts": dict(sorted(tool_counts.items())),
            "mutations": len(mutation_events),
            "validations": len(validation_events),
            "last_mutation_step": last_mutation,
            "validation_after_last_mutation": validation_after_last,
            "repeated_validations_without_mutation": repeated_validations,
            "normal_final": normal_final,
            "subagent_trajectories": len(trajectory.get("subagent_trajectories") or []) if isinstance(trajectory, dict) else None,
        },
        "delivery": patch,
        "exception_type": exception_type or None,
        "stop_reason": stop_reason or None,
        "artifacts": artifacts,
        "provenance": {
            "task_name": provenance(result_path, "task_name", adapter, "complete" if task_name else "missing"),
            "task_checksum": provenance(result_path, "task_checksum", adapter, "complete" if task_checksum else "missing"),
            "reward": provenance(reward_path if verifier_rewards else result_path, "reward", adapter, "complete" if reward is not None else "missing"),
            "duration_sec": provenance(result_path, "started_at/finished_at", adapter, "complete" if duration is not None else "missing"),
            "tokens": token_prov,
        },
        "limitations": token_warnings,
    }
    return record, candidates


def is_trial_dir(path: Path) -> bool:
    return (path / "result.json").is_file() and ((path / "agent").exists() or (path / "verifier").exists())


def trial_dirs_for_job(path: Path) -> list[Path]:
    return sorted(child for child in path.iterdir() if child.is_dir() and (child / "result.json").is_file())


def determine_mode(inputs: Sequence[Path], requested: str) -> str:
    if requested != "auto":
        return requested
    if len(inputs) > 1:
        return "paired"
    return "trial" if is_trial_dir(inputs[0]) else "job"


def collect(inputs: Sequence[Path], mode: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[list[dict[str, Any]]]]:
    all_records: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    job_records: list[list[dict[str, Any]]] = []
    for input_path in inputs:
        roots = [input_path] if mode == "trial" else trial_dirs_for_job(input_path)
        if not roots:
            raise ValueError(f"no trial directories found under {input_path}")
        current: list[dict[str, Any]] = []
        job_root = input_path.parent if mode == "trial" else input_path
        for root in roots:
            record, candidates = extract_trial(root, job_root)
            current.append(record)
            all_records.append(record)
            all_candidates.extend(candidates)
        job_records.append(current)
    return all_records, all_candidates, job_records


def task_family(record: dict[str, Any]) -> str:
    name = str(record.get("task_name") or record.get("trial") or "unknown").split("/")[-1]
    return name.split("-", 1)[0]


def endpoint(record: dict[str, Any]) -> str:
    score = record["score"]["reconciled"]
    if record.get("exception_type"):
        return "exception"
    if (score.get("p2p_failed") or 0) > 0:
        return "regression"
    if (score.get("f2p_failed") or 0) > 0:
        return "target-unresolved"
    return "verifier-rejected"


def passed(record: dict[str, Any]) -> bool:
    reward = nested(record, "score", "reconciled", "reward")
    return reward is not None and reward > 0


def add_high_resource_candidates(records: Sequence[dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    totals = sorted(
        value for value in (nested(record, "tokens", "total_tokens_excluding_cache") for record in records)
        if value is not None
    )
    if not totals:
        return
    index = max(0, math.ceil(0.75 * len(totals)) - 1)
    threshold = totals[index]
    for record in records:
        total = nested(record, "tokens", "total_tokens_excluding_cache")
        if not passed(record) and total is not None and total >= threshold:
            candidates.append(make_candidate(record["trial_key"], "tokens", "FM-11", f"failed at or above job P75 total tokens={threshold}", [str(Path(record["trial_root"]) / "result.json")]))


def comparison_grade(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not left.get("task_name") or left.get("task_name") != right.get("task_name"):
        return "ineligible", ["task_name mismatch or missing"]
    checksum_equal = bool(left.get("task_checksum") and left.get("task_checksum") == right.get("task_checksum"))
    baseline_equal = bool(left.get("baseline") and left.get("baseline") == right.get("baseline"))
    verifier_equal = bool(left.get("verifier_fingerprint") and left.get("verifier_fingerprint") == right.get("verifier_fingerprint"))
    prompt_equal = bool(left.get("prompt_fingerprint") and left.get("prompt_fingerprint") == right.get("prompt_fingerprint"))
    verifier_conflict = bool(left.get("verifier_fingerprint") and right.get("verifier_fingerprint") and not verifier_equal)
    baseline_conflict = bool(left.get("baseline") and right.get("baseline") and not baseline_equal)
    if verifier_conflict or baseline_conflict:
        if verifier_conflict:
            reasons.append("verifier fingerprint mismatch")
        if baseline_conflict:
            reasons.append("baseline mismatch")
        return "ineligible", reasons
    if checksum_equal and baseline_equal and verifier_equal:
        return "strict", ["checksum, baseline and verifier fingerprint match"]
    if verifier_equal and (checksum_equal or baseline_equal or prompt_equal):
        if not checksum_equal:
            reasons.append("checksum differs or missing")
        if not baseline_equal:
            reasons.append("baseline differs or missing")
        if not prompt_equal:
            reasons.append("prompt fingerprint differs or missing")
        reasons.append("verifier identity plus another semantic identity signal match")
        return "conditional", reasons
    reasons.append("task name matches but semantic identity evidence is insufficient")
    return "descriptive_only", reasons


def build_comparability(jobs: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    if len(jobs) != 2:
        return []
    left_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    right_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in jobs[0]:
        left_map[str(record.get("task_name") or f"<missing>:{record['trial']}")].append(record)
    for record in jobs[1]:
        right_map[str(record.get("task_name") or f"<missing>:{record['trial']}")].append(record)
    rows: list[dict[str, Any]] = []
    for task in sorted(set(left_map) | set(right_map)):
        left_items, right_items = sorted(left_map.get(task, []), key=lambda item: item["trial"]), sorted(right_map.get(task, []), key=lambda item: item["trial"])
        count = max(len(left_items), len(right_items))
        for index in range(count):
            left = left_items[index] if index < len(left_items) else None
            right = right_items[index] if index < len(right_items) else None
            if not left or not right:
                rows.append({
                    "task_name": task,
                    "left_trial_key": left["trial_key"] if left else None,
                    "right_trial_key": right["trial_key"] if right else None,
                    "grade": "ineligible",
                    "reasons": "missing counterpart",
                    "outcome_quadrant": "unpaired",
                })
                continue
            grade, reasons = comparison_grade(left, right)
            left_pass, right_pass = passed(left), passed(right)
            quadrant = "both_pass" if left_pass and right_pass else "left_only" if left_pass else "right_only" if right_pass else "both_fail"
            rows.append({
                "task_name": task,
                "left_trial_key": left["trial_key"],
                "right_trial_key": right["trial_key"],
                "grade": grade,
                "reasons": "; ".join(reasons),
                "outcome_quadrant": quadrant,
                "left_reward": nested(left, "score", "reconciled", "reward"),
                "right_reward": nested(right, "score", "reconciled", "reward"),
                "left_duration_sec": nested(left, "latency", "duration_sec"),
                "right_duration_sec": nested(right, "latency", "duration_sec"),
                "left_total_tokens": nested(left, "tokens", "total_tokens_excluding_cache"),
                "right_total_tokens": nested(right, "tokens", "total_tokens_excluding_cache"),
                "left_censored": nested(left, "latency", "censored"),
                "right_censored": nested(right, "latency", "censored"),
            })
    return rows


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def bootstrap_interval(values: Sequence[float], seed: int = BOOTSTRAP_SEED, samples: int = BOOTSTRAP_SAMPLES) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    medians = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        medians.append(statistics.median(sample))
    low, high = percentile(medians, 0.025), percentile(medians, 0.975)
    return [round(float(low), 6), round(float(high), 6)] if low is not None and high is not None else None


def comparison_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["grade"] in {"strict", "conditional"}]
    stats: dict[str, Any] = {
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "eligible_pairs": len(eligible),
        "grade_counts": dict(sorted(Counter(row["grade"] for row in rows).items())),
        "outcome_quadrants": dict(sorted(Counter(row["outcome_quadrant"] for row in eligible).items())),
        "metrics": {},
    }
    pass_differences = [
        (1.0 if row["right_reward"] and row["right_reward"] > 0 else 0.0) - (1.0 if row["left_reward"] and row["left_reward"] > 0 else 0.0)
        for row in eligible if row["left_reward"] is not None and row["right_reward"] is not None
    ]
    stats["pass_rate_delta"] = {
        "n_available": len(pass_differences),
        "n_missing": len(eligible) - len(pass_differences),
        "median_or_mean_delta": round(statistics.mean(pass_differences), 6) if pass_differences else None,
        "bootstrap_95_interval": bootstrap_interval(pass_differences),
    }
    for name, left_key, right_key, require_completed in (
        ("duration_sec", "left_duration_sec", "right_duration_sec", True),
        ("total_tokens", "left_total_tokens", "right_total_tokens", False),
    ):
        pairs = []
        for row in eligible:
            left, right = row.get(left_key), row.get(right_key)
            if left is None or right is None or (require_completed and (row.get("left_censored") or row.get("right_censored"))):
                continue
            pairs.append((float(left), float(right)))
        differences = [right - left for left, right in pairs]
        ratios = [right / left for left, right in pairs if left != 0]
        stats["metrics"][name] = {
            "n_available": len(pairs),
            "n_missing": len(eligible) - len(pairs),
            "left_median": round(statistics.median(left for left, _ in pairs), 6) if pairs else None,
            "right_median": round(statistics.median(right for _, right in pairs), 6) if pairs else None,
            "paired_median_difference": round(statistics.median(differences), 6) if differences else None,
            "paired_median_ratio": round(statistics.median(ratios), 6) if ratios else None,
            "difference_bootstrap_95_interval": bootstrap_interval(differences),
        }
    return stats


def round_robin(items: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in sorted(items, key=lambda record: (record.get("task_name") or "", record["trial"])):
        buckets[(endpoint(item), task_family(item))].append(item)
    selected: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(selected) < min(limit, len(items)):
        progressed = False
        for key in keys:
            if buckets[key]:
                selected.append(buckets[key].pop(0))
                progressed = True
                if len(selected) == min(limit, len(items)):
                    break
        if not progressed:
            break
    return selected


def single_selection(records: Sequence[dict[str, Any]], depth: str) -> list[dict[str, Any]]:
    if depth == "metrics":
        return []
    failures = [record for record in records if not passed(record)]
    chosen_failures = failures if depth == "full" or len(failures) <= 12 else round_robin(failures, 12)
    rows = [{
        "selection_unit": "trial", "task_name": record.get("task_name"), "left_trial_key": record["trial_key"],
        "right_trial_key": None, "outcome": "fail", "reason": "all analyzable failures" if depth == "full" else "deterministic failure coverage",
    } for record in chosen_failures]
    successes = [record for record in records if passed(record)]
    controls: list[dict[str, Any]] = []
    failure_families = sorted({task_family(record) for record in failures})
    control_limit = len(failure_families) if depth == "full" else min(4, len(failure_families))
    for family in failure_families:
        available = sorted(
            [record for record in successes if task_family(record) == family],
            key=lambda record: (nested(record, "tokens", "total_tokens_excluding_cache") is None, nested(record, "tokens", "total_tokens_excluding_cache") or 0, record["trial"]),
        )
        if available:
            controls.append(available[(len(available) - 1) // 2])
        if len(controls) >= control_limit:
            break
    if depth == "standard" and len(controls) < 4:
        used = {record["trial_key"] for record in controls}
        extras = sorted([record for record in successes if record["trial_key"] not in used], key=lambda record: (record.get("task_name") or "", record["trial"]))
        controls.extend(extras[: 4 - len(controls)])
    rows.extend({
        "selection_unit": "trial", "task_name": record.get("task_name"), "left_trial_key": record["trial_key"],
        "right_trial_key": None, "outcome": "pass", "reason": "success control from failure-represented task family",
    } for record in controls)
    return rows


def paired_selection(comparability: Sequence[dict[str, Any]], depth: str) -> list[dict[str, Any]]:
    if depth == "metrics":
        return []
    candidates = [row for row in comparability if row["grade"] != "ineligible"]
    if depth == "full":
        selected = [row for row in candidates if row["outcome_quadrant"] != "both_pass"]
        reason = "all paired failures or flips"
    else:
        preferred = [row for row in candidates if row["grade"] in {"strict", "conditional"}]
        pool = preferred or candidates
        strata = {
            "left_only": sorted([row for row in pool if row["outcome_quadrant"] == "left_only"], key=lambda row: row["task_name"]),
            "right_only": sorted([row for row in pool if row["outcome_quadrant"] == "right_only"], key=lambda row: row["task_name"]),
            "both_fail": sorted([row for row in pool if row["outcome_quadrant"] == "both_fail"], key=lambda row: row["task_name"]),
            "both_pass": sorted([row for row in pool if row["outcome_quadrant"] == "both_pass"], key=lambda row: row["task_name"]),
        }
        selected = []
        for key in ("left_only", "right_only"):
            selected.extend(strata[key][:2])
        selected.extend(strata["both_fail"][:2])
        selected.extend(strata["both_pass"][:2])
        seen = {row["task_name"] for row in selected}
        leftovers = sorted([row for row in pool if row["task_name"] not in seen], key=lambda row: (row["outcome_quadrant"], row["task_name"]))
        selected.extend(leftovers[: max(0, 8 - len(selected))])
        selected = selected[:8]
        reason = "paired outcome quadrants with deterministic fallback"
    return [{
        "selection_unit": "pair",
        "task_name": row["task_name"],
        "left_trial_key": row["left_trial_key"],
        "right_trial_key": row["right_trial_key"],
        "outcome": row["outcome_quadrant"],
        "reason": f"{reason}; comparability={row['grade']}",
    } for row in selected]


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    temporary.replace(path)


def flatten_trial(record: dict[str, Any]) -> dict[str, Any]:
    score = record["score"]["reconciled"]
    return {
        "trial_key": record["trial_key"], "job": record["job"], "trial": record["trial"],
        "task_name": record["task_name"], "task_checksum": record["task_checksum"], "adapter": record["adapter"],
        "agent": record["agent"], "model": record["model"], "health": record["health"], "coverage": record["coverage"],
        "reward": score["reward"], "partial": score["partial"], "f2p_passed": score["f2p_passed"], "f2p_total": score["f2p_total"],
        "p2p_passed": score["p2p_passed"], "p2p_total": score["p2p_total"],
        "input_tokens": record["tokens"]["input_tokens"], "output_tokens": record["tokens"]["output_tokens"],
        "cache_read_tokens": record["tokens"]["cache_read_tokens"], "cache_creation_tokens": record["tokens"]["cache_creation_tokens"],
        "duration_sec": record["latency"]["duration_sec"], "censored": record["latency"]["censored"],
        "steps": record["process"]["steps"], "tool_calls": record["process"]["tool_calls"], "mutations": record["process"]["mutations"],
        "validations": record["process"]["validations"], "validation_after_last_mutation": record["process"]["validation_after_last_mutation"],
        "patch_path": record["delivery"]["path"], "patch_sha256": record["delivery"]["sha256"], "trial_root": record["trial_root"],
    }


def summary_report(records: Sequence[dict[str, Any]], candidates: Sequence[dict[str, Any]], selection: Sequence[dict[str, Any]], mode: str, depth: str) -> str:
    health_counts = Counter(record["health"] for record in records)
    adapter_counts = Counter(record["adapter"] for record in records)
    known_rewards = [nested(record, "score", "reconciled", "reward") for record in records if nested(record, "score", "reconciled", "reward") is not None]
    passed_count = sum(value > 0 for value in known_rewards)
    lines = [
        "# Agent 轨迹审计报告",
        "",
        "> 本文件由确定性提取器初始化，包含全量 measurement 和待人工裁决候选。请在复核原始证据后补充 mechanism、root cause 与控制建议。",
        "",
        "## 范围",
        "",
        f"- 方法版本：`{METHODOLOGY_VERSION}`；规则版本：`{RULE_VERSION}`",
        f"- 模式：`{mode}`；深度：`{depth}`",
        f"- Trial 数：{len(records)}；有 verifier reward：{len(known_rewards)}；通过：{passed_count}；失败：{len(known_rewards) - passed_count}",
        f"- Adapter：`{json.dumps(dict(sorted(adapter_counts.items())), ensure_ascii=False)}`",
        f"- 健康状态：`{json.dumps(dict(sorted(health_counts.items())), ensure_ascii=False)}`",
        f"- 启发式候选：{len(candidates)}；深读选择：{len(selection)}",
        "",
        "## 结论边界",
        "",
        "- `generated/` 中的候选不是作弊、环境责任或根因裁决。",
        "- 标准模式的深读样本不能用于估计全量根因比例。" if depth == "standard" else "- 完整模式仍需对每个失败完成人工因果闭环后，才能聚合根因比例.",
        "- 配对差异是观察性结果；只有 `strict`/`conditional` pair 进入区间统计，不代表单变量因果优越性。",
        "",
        "## 待人工完成",
        "",
        "1. 复核 health、可比性和 raw/reconciled truth。",
        "2. 按专项方法裁决环境、评测完整性、Token、耗时和交付链候选。",
        "3. 对 selection 中的 trace 深读，记录首个 consequential break、反证和成功对照。",
        "4. 将裁决写入 `adjudicated/findings.jsonl`，再更新本报告。",
        "",
    ]
    return "\n".join(lines)


def output_inside_input(output: Path, inputs: Sequence[Path]) -> bool:
    for input_path in inputs:
        if output == input_path or input_path in output.parents:
            return True
    return False


def parse_focus(value: str) -> set[str]:
    allowed = {"health", "environment", "integrity", "tokens", "latency", "score", "process"}
    if value == "all":
        return allowed
    selected = {item.strip() for item in value.split(",") if item.strip()}
    unknown = selected - allowed
    if unknown:
        raise ValueError(f"unknown focus values: {', '.join(sorted(unknown))}")
    return selected | {"health"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    inputs = [path.resolve() for path in args.inputs]
    output = args.output.resolve()
    for path in inputs:
        if not path.is_dir():
            raise ValueError(f"input is not a directory: {path}")
    if output_inside_input(output, inputs):
        raise ValueError("output directory must not be inside an input job/trial")
    mode = determine_mode(inputs, args.mode)
    if mode == "paired" and len(inputs) != 2:
        raise ValueError("paired mode requires exactly two job directories")
    if mode == "trial" and len(inputs) != 1:
        raise ValueError("trial mode requires exactly one trial directory")
    focus = parse_focus(args.focus)
    depth = "full" if mode == "trial" else args.depth

    records, candidates, jobs = collect(inputs, mode)
    add_high_resource_candidates(records, candidates)
    candidates = dedupe_candidates([candidate for candidate in candidates if candidate["focus"] in focus])
    comparability = build_comparability(jobs) if mode == "paired" else []
    stats = comparison_stats(comparability) if mode == "paired" else {
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "eligible_pairs": 0,
        "grade_counts": {},
        "outcome_quadrants": {},
        "metrics": {},
    }
    if mode == "paired":
        selection = paired_selection(comparability, depth)
    elif mode == "trial":
        record = records[0]
        selection = [{
            "selection_unit": "trial",
            "task_name": record.get("task_name"),
            "left_trial_key": record["trial_key"],
            "right_trial_key": None,
            "outcome": "pass" if passed(record) else "fail",
            "reason": "single trial always receives a complete deep read",
        }]
    else:
        selection = single_selection(records, depth)

    generated = output / "generated"
    adjudicated = output / "adjudicated"
    generated.mkdir(parents=True, exist_ok=True)
    adjudicated.mkdir(parents=True, exist_ok=True)

    input_manifest = []
    for path in inputs:
        root_result = path / "result.json"
        input_manifest.append({"path": str(path), "result": file_record(root_result)})
    manifest = {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "rule_version": RULE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "depth": depth,
        "focus": sorted(focus),
        "inputs": input_manifest,
        "output": str(output),
        "trial_count": len(records),
        "adapter_counts": dict(sorted(Counter(record["adapter"] for record in records).items())),
        "selection_rule": "trial=full; single-job=all failures if <=12 else deterministic 12 plus <=4 controls; paired=4 flips+2 common failures+2 common passes with stable fallback",
        "bootstrap": {"seed": BOOTSTRAP_SEED, "samples": BOOTSTRAP_SAMPLES},
        "redaction": {
            "enabled": True,
            "policy": "allowlisted config fields; credential assignments, bearer values and sk-* tokens masked; evidence snippets length limited",
        },
        "warnings": [
            "Candidates are heuristic and require raw-evidence adjudication.",
            "Unknown schemas remain null/degraded; missing values are never converted to zero.",
            "Standard deep-read samples do not estimate mechanism prevalence.",
        ],
    }
    write_json(generated / "manifest.json", manifest)
    write_jsonl(generated / "trials.jsonl", records)
    flat = [flatten_trial(record) for record in records]
    trial_fields = list(flat[0].keys()) if flat else ["trial_key"]
    write_csv(generated / "trials.csv", flat, trial_fields)
    comparison_fields = [
        "task_name", "left_trial_key", "right_trial_key", "grade", "reasons", "outcome_quadrant",
        "left_reward", "right_reward", "left_duration_sec", "right_duration_sec", "left_total_tokens", "right_total_tokens",
        "left_censored", "right_censored",
    ]
    write_csv(generated / "comparability.csv", comparability, comparison_fields)
    write_json(generated / "comparison-stats.json", stats)
    write_jsonl(generated / "candidates.jsonl", candidates)
    selection_fields = ["selection_unit", "task_name", "left_trial_key", "right_trial_key", "outcome", "reason"]
    write_csv(generated / "selection.csv", selection, selection_fields)

    findings_path = adjudicated / "findings.jsonl"
    if not findings_path.exists():
        findings_path.write_text("", encoding="utf-8")
    report_path = output / "report.md"
    if not report_path.exists():
        report_path.write_text(summary_report(records, candidates, selection, mode, depth), encoding="utf-8")

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "mode": mode,
        "depth": depth,
        "output": str(output),
        "trials": len(records),
        "candidates": len(candidates),
        "selected": len(selection),
        "health": dict(sorted(Counter(record["health"] for record in records).items())),
        "comparability": dict(sorted(Counter(row["grade"] for row in comparability).items())),
        "manual_files_preserved": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, metavar="INPUT")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("auto", "trial", "job", "paired"), default="auto")
    parser.add_argument("--depth", choices=("metrics", "standard", "full"), default="standard")
    parser.add_argument("--focus", default="all", help="all or comma-separated: health,environment,integrity,tokens,latency,score,process")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = run(args)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
