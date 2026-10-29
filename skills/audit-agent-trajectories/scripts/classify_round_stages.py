#!/usr/bin/env python3
"""Project normalized model rounds into heuristic E/B/I/V/P stages."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.dont_write_bytecode = True
import classify_round_actions as actions


SCRIPT_VERSION = "1.0.0"
INPUT_SCHEMA_VERSION = "trajectory-events/1"
SCHEMA_VERSION = "round-stages/1"
METHODOLOGY_VERSION = "2.8.1"
RULE_VERSION = "ebivp-stage-projection/1.0"


def validation_statuses(calls: Sequence[dict[str, Any]]) -> dict[str, str]:
    by_round: dict[str, list[str]] = defaultdict(list)
    for call in calls:
        if "verification" in (call.get("operation_tags") or []):
            by_round[str(call.get("round_key"))].append(str(call.get("result_status") or "unknown"))
    output = {}
    for key, statuses in by_round.items():
        if "failure" in statuses:
            output[key] = "failure"
        elif statuses and all(status == "success" for status in statuses):
            output[key] = "success"
        else:
            output[key] = "unknown"
    return output


def span(label: str, start: int | None, end: int | None) -> dict[str, Any] | None:
    if start is None or end is None or start > end:
        return None
    return {"stage": label, "start_round": start, "end_round": end, "rounds": end - start + 1}


def stage_trace(rows: Sequence[dict[str, Any]], status_by_round: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda row: int(row.get("round_index") or 0))
    total = len(ordered)
    mutation_turns = [
        int(row["round_index"])
        for row in ordered
        if "editing" in (row.get("operation_tags") or [])
    ]
    validations = [
        (int(row["round_index"]), status_by_round.get(str(row.get("round_key")), "unknown"))
        for row in ordered
        if "verification" in (row.get("operation_tags") or [])
    ]
    first_mutation = min(mutation_turns, default=None)
    first_observed_validation = min((turn for turn, _ in validations), default=None)
    post_mutation = [
        (turn, status)
        for turn, status in validations
        if first_mutation is None or turn >= first_mutation
    ]
    first_validation = min((turn for turn, _ in post_mutation), default=None)

    stable_green = None
    for position, (turn, status) in enumerate(post_mutation):
        later_statuses = [item_status for _, item_status in post_mutation[position:]]
        if status == "success" and all(item_status == "success" for item_status in later_statuses):
            stable_green = turn
            break

    spans: list[dict[str, Any]] = []
    if first_mutation is None:
        exploration_end = first_observed_validation - 1 if first_observed_validation else total
        for item in (
            span("E", 1, exploration_end),
            span("V", first_observed_validation, stable_green or total),
            span("P", stable_green + 1 if stable_green else None, total),
        ):
            if item:
                spans.append(item)
    else:
        baseline_start = (
            first_observed_validation
            if first_observed_validation is not None and first_observed_validation < first_mutation
            else None
        )
        exploration_end = baseline_start - 1 if baseline_start is not None else first_mutation - 1
        implementation_end = first_validation - 1 if first_validation else total
        for item in (
            span("E", 1, exploration_end),
            span("B", baseline_start, first_mutation - 1),
            span("I", first_mutation, implementation_end),
            span("V", first_validation, stable_green or total),
            span("P", stable_green + 1 if stable_green else None, total),
        ):
            if item:
                spans.append(item)

    stage_by_round = {
        round_index: item["stage"]
        for item in spans
        for round_index in range(int(item["start_round"]), int(item["end_round"]) + 1)
    }
    classified = [{**row, "stage": stage_by_round.get(int(row.get("round_index") or 0), "unknown")} for row in ordered]
    boundary = {
        "job": ordered[0].get("job") if ordered else None,
        "trial_key": ordered[0].get("trial_key") if ordered else None,
        "task_name": ordered[0].get("task_name") if ordered else None,
        "session_id": ordered[0].get("session_id") if ordered else None,
        "actor_role": ordered[0].get("actor_role") if ordered else None,
        "rounds": total,
        "first_mutation_round": first_mutation,
        "first_observed_validation_round": first_observed_validation,
        "first_post_mutation_validation_round": first_validation,
        "stable_green_round": stable_green,
        "validation_rounds": len(validations),
        "failed_validation_rounds": sum(status == "failure" for _, status in validations),
        "unknown_validation_rounds": sum(status == "unknown" for _, status in validations),
        "stage_spans": spans,
        "stage_string": " ".join(
            f"{item['stage']}{item['start_round']}" if item["start_round"] == item["end_round"]
            else f"{item['stage']}{item['start_round']}-{item['end_round']}"
            for item in spans
        ),
        "status": "heuristic",
    }
    return boundary, classified


def project_stages(
    rounds: Sequence[dict[str, Any]],
    calls: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    action_rows = actions.classify_rows(rounds, calls)
    status_by_round = validation_statuses(calls)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in action_rows:
        grouped[(str(row.get("trial_key")), str(row.get("session_id")))].append(row)
    boundaries = []
    classified = []
    for key in sorted(grouped):
        boundary, rows = stage_trace(grouped[key], status_by_round)
        boundaries.append(boundary)
        classified.extend(rows)
    return boundaries, classified


def stage_views(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_job[str(row.get("job"))].append(row)
    output = {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "definitions": {
            "E": "exploration before baseline validation or first mutation",
            "B": "baseline validation window before first mutation",
            "I": "implementation from first mutation until first post-mutation validation",
            "V": "validation and rework until stable green, or end when stable green is absent",
            "P": "work after stable green",
        },
        "jobs": {},
    }
    for job, job_rows in sorted(by_job.items()):
        counts = Counter(str(row.get("stage")) for row in job_rows)
        output["jobs"][job] = {"rounds": len(job_rows), "stages": dict(sorted(counts.items()))}
    return output


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
    _, rounds, calls = actions.load_normalized(source)
    boundaries, classified = project_stages(rounds, calls)
    views = stage_views(classified)

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
        "round_count": len(classified),
        "trace_count": len(boundaries),
        "include_rounds": include_rounds,
        "scope": "heuristic E/B/I/V/P projection from observed mutation and validation events; not a runtime-native phase",
    }
    write_json(output / "round-stages.json", {
        "manifest": result_manifest,
        "summary": views,
        "boundaries": boundaries,
    })
    if include_rounds:
        write_jsonl(output / "staged-rounds.jsonl", classified)
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "output": str(output),
        "rounds": len(classified),
        "traces": len(boundaries),
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
