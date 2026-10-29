#!/usr/bin/env python3
"""Classify normalized model rounds into mutually exclusive action categories."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_VERSION = "1.0.0"
INPUT_SCHEMA_VERSION = "trajectory-events/1"
SCHEMA_VERSION = "round-actions/1"
METHODOLOGY_VERSION = "2.8.1"
RULE_VERSION = "round-action-classification/1.0"


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSONL at {path}:{line_number}: {error}") from error
                if not isinstance(value, dict):
                    raise ValueError(f"expected object at {path}:{line_number}")
                rows.append(value)
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    return rows


def load_normalized(source: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    packed = source / "trajectory-events.jsonl"
    if packed.is_file():
        records = load_jsonl(packed)
        manifest_row = next((row for row in records if row.get("record_type") == "manifest"), None)
        manifest = manifest_row.get("data") if isinstance(manifest_row, dict) else None
        rounds = [
            {key: value for key, value in row.items() if key != "record_type"}
            for row in records if row.get("record_type") == "round"
        ]
        calls = [
            {key: value for key, value in row.items() if key != "record_type"}
            for row in records if row.get("record_type") == "tool_call"
        ]
    else:
        manifest = load_json(source / "manifest.json", {})
        rounds = load_jsonl(source / "rounds.jsonl")
        calls = load_jsonl(source / "tool-calls.jsonl")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError(f"expected {INPUT_SCHEMA_VERSION} normalized events under {source}")
    return manifest, rounds, calls


def classify(tags: set[str], has_calls: bool) -> str:
    if "verification" in tags:
        return "verification"
    if "editing" in tags:
        return "editing"
    if "exploration" in tags:
        return "exploration"
    return "other"


def classify_rows(
    rounds: Sequence[dict[str, Any]],
    calls: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    calls_by_round: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        calls_by_round[str(call.get("round_key"))].append(call)
    output = []
    for request in rounds:
        key = str(request.get("round_key"))
        round_calls = calls_by_round.get(key, [])
        tags = {
            str(tag)
            for call in round_calls
            for tag in (call.get("operation_tags") or [])
        }
        action = classify(tags, bool(round_calls))
        output.append({
            **request,
            "methodology_version": METHODOLOGY_VERSION,
            "action_schema_version": SCHEMA_VERSION,
            "action_rule_version": RULE_VERSION,
            "action": action,
            "operation_tags": sorted(tags),
        })
    return output


def action_views(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_job[str(row.get("job"))].append(row)
    views: dict[str, Any] = {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "classification_priority": [
            "verification", "editing", "exploration", "other",
        ],
        "definition": "matches BitFun diagnostics precedence: verification > editing > exploration > other",
        "jobs": {},
    }
    for job, job_rows in sorted(by_job.items()):
        total = len(job_rows)
        detailed = Counter(str(row.get("action")) for row in job_rows)
        views["jobs"][job] = {
            "rounds": total,
            "actions": dict(sorted(detailed.items())),
        }
    return views


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.normalized.resolve()
    output = args.output.resolve()
    include_rounds = bool(getattr(args, "include_rounds", False))
    _, rounds, calls = load_normalized(source)
    rows = classify_rows(rounds, calls)
    views = action_views(rows)

    output.mkdir(parents=True, exist_ok=True)
    result_manifest = {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "rule_version": RULE_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": str(source),
        "output": str(output),
        "round_count": len(rows),
        "include_rounds": include_rounds,
        "scope": "deterministic action classification; categories describe observable tool composition, not intent, quality, or root cause",
    }
    write_json(output / "round-actions.json", {"manifest": result_manifest, "summary": views})
    if include_rounds:
        write_jsonl(output / "classified-rounds.jsonl", rows)
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "output": str(output),
        "rounds": len(rows),
        "jobs": len(views["jobs"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized", type=Path, metavar="NORMALIZED_OUTPUT")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-rounds", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
