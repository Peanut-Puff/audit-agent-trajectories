#!/usr/bin/env python3
"""Build the deterministic AEO runtime profile from the canonical skill source."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "audit-agent-trajectories"
PROMPT = SKILL / "references" / "adapters" / "aeo-runtime-prompt.md"
DEFAULT_OUTPUT = SKILL / "runtime" / "aeo-profile.json"
PROFILE_SCHEMA_VERSION = "aeo-analysis-methodology-profile/1.0"
REQUEST_SCHEMA_VERSION = "aeo-audit-agent-input/1.0"
SUPPORTED_TASK_TYPES = (
    "semantic_summary",
    "behavior_explanation",
    "root_cause_hypothesis",
    "paired_difference_summary",
    "job_health_summary",
    "job_score_summary",
    "job_environment_summary",
    "job_integrity_summary",
    "job_token_cost_summary",
    "job_latency_summary",
    "job_delivery_summary",
    "job_anomaly_summary",
    "job_attribution_summary",
    "job_data_health_summary",
    "job_outcome_summary",
    "job_verifier_summary",
    "job_execution_health_summary",
    "job_latency_efficiency_summary",
    "job_model_resource_summary",
    "job_tool_process_summary",
    "job_delivery_validation_summary",
    "job_risk_optimization_summary",
    "job_score_optimization",
    "job_token_optimization",
    "job_latency_optimization",
    "job_other_optimization",
)


def profile_bytes() -> bytes:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    template = PROMPT.read_text(encoding="utf-8").strip()
    placeholder = "{{METHODOLOGY_VERSION}}"
    if template.count(placeholder) != 1:
        raise ValueError("AEO runtime prompt must contain one methodology version placeholder")
    profile = {
        "externalAgent": "audit-agent-trajectories",
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "methodologyVersion": version,
        "requestSchemaVersion": REQUEST_SCHEMA_VERSION,
        "responseLanguage": "zh-CN",
        "supportedTaskTypes": list(SUPPORTED_TASK_TYPES),
        "systemPrompt": template.replace(placeholder, version),
    }
    return (json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="build the AEO methodology runtime profile")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = profile_bytes()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            print(f"AEO profile is stale: {args.output}", file=sys.stderr)
            return 1
        print(f"AEO profile is current: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
