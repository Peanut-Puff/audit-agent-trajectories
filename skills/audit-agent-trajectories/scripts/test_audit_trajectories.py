#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("audit_trajectories.py")
PROFILE = Path(__file__).parents[1] / "runtime" / "aeo-profile.json"
SPEC = importlib.util.spec_from_file_location("audit_trajectories", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_trial(
    job: Path,
    name: str,
    *,
    adapter: str = "bitfun",
    reward: int = 1,
    checksum: str = "checksum-a",
    patch_rel: str = "artifacts/model.patch",
    include_tokens: bool = True,
    exception: str | None = None,
    extra_calls: list[dict[str, object]] | None = None,
) -> Path:
    root = job / name
    root.mkdir(parents=True)
    agent_name = adapter if adapter != "harbor-generic" else "custom-agent"
    result = {
        "trial_name": name,
        "id": f"id-{name}",
        "task_name": f"dataset/{name}",
        "task_checksum": checksum,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "exception_info": {"exception_type": exception} if exception else None,
        "agent_result": {
            "n_input_tokens": 100 if include_tokens else None,
            "n_output_tokens": 10 if include_tokens else None,
            "n_cache_tokens": 80 if include_tokens else None,
            "cost_usd": None,
            "metadata": {
                "aeo_model_usage": {
                    "schemaVersion": "harbor-model-usage/1.3",
                    "requestCount": 1,
                    "coveredRequestCount": 1,
                    "inputTokensComplete": True,
                    "outputTokensComplete": True,
                    "collectionComplete": True,
                }
            } if include_tokens else {},
        },
        "verifier_result": {
            "rewards": {
                "reward": reward,
                "partial": float(reward),
                "f2p_total": 2,
                "f2p_passed": 2 if reward else 1,
                "p2p_total": 1,
                "p2p_passed": 1,
            }
        },
    }
    dump(root / "result.json", result)
    dump(root / "config.json", {
        "agent": {"name": agent_name, "model_name": "model-x", "kwargs": {"api_key": "super-secret-value"}},
        "environment": {"type": "docker", "env": {"AUTH_TOKEN": "also-secret"}},
    })
    command_key = "cmd" if adapter == "bitfun" else "command"
    function_name = "ExecCommand" if adapter == "bitfun" else "bash"
    calls = [
        {"function_name": function_name, "arguments": {command_key: "apply_patch <<'PATCH'\nPATCH"}},
        {"function_name": function_name, "arguments": {command_key: "pytest -q"}},
    ]
    calls.extend(extra_calls or [])
    steps = [
        {"step_id": 1, "source": "user", "message": "fix the behavior", "timestamp": "2026-01-01T00:00:01Z"},
    ]
    for index, call in enumerate(calls, start=2):
        steps.append({
            "step_id": index,
            "source": "agent",
            "message": "",
            "timestamp": f"2026-01-01T00:00:{index:02d}Z",
            "tool_calls": [call],
            "observation": "completed successfully",
        })
    steps.append({"step_id": len(steps) + 1, "source": "agent", "message": "Implemented and tests pass.", "timestamp": "2026-01-01T00:00:20Z"})
    dump(root / "agent" / "trajectory.json", {
        "agent": {"name": agent_name, "version": "1.0", "model_name": "model-x"},
        "steps": steps,
        "final_metrics": {},
    })
    if adapter == "bitfun":
        (root / "agent" / "bitfun").mkdir(parents=True, exist_ok=True)
    patch = root / patch_rel
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n+fixed = True\n", encoding="utf-8")
    baseline = root / "agent" / "patch" / "git-baseline-commit.txt"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text("abc123\n", encoding="utf-8")
    dump(root / "verifier" / "reward.json", result["verifier_result"]["rewards"])
    dump(root / "verifier" / "ctrf.json", {
        "results": {
            "tests": [
                {"name": "target test", "suite": "feature", "status": "passed" if reward else "failed"},
                {"name": "regression", "suite": "base", "status": "passed"},
            ]
        }
    })
    (root / "trial.log").write_text("trial completed\n", encoding="utf-8")
    return root


class AuditTrajectoriesTests(unittest.TestCase):
    def test_aeo_runtime_profile_uses_current_methodology_and_chinese_output(self) -> None:
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))

        self.assertEqual(profile["externalAgent"], "audit-agent-trajectories")
        self.assertEqual(profile["schemaVersion"], "aeo-analysis-methodology-profile/1.0")
        self.assertEqual(profile["methodologyVersion"], "2.9.0")
        self.assertEqual(profile["requestSchemaVersion"], "aeo-audit-agent-input/1.0")
        self.assertEqual(profile["responseLanguage"], "zh-CN")
        self.assertIn("job_attribution_summary", profile["supportedTaskTypes"])
        self.assertIn("job_integrity_summary", profile["supportedTaskTypes"])
        self.assertIn("job_data_health_summary", profile["supportedTaskTypes"])
        self.assertIn("job_risk_optimization_summary", profile["supportedTaskTypes"])
        self.assertIn("关键结论", profile["systemPrompt"])
        self.assertIn("影响范围", profile["systemPrompt"])
        self.assertIn("无需动作", profile["systemPrompt"])
        self.assertIn("caseCohorts", profile["systemPrompt"])
        self.assertIn("prioritizedFindings", profile["systemPrompt"])
        self.assertIn("success Case", profile["systemPrompt"])
        self.assertIn("delivery_evidence_unavailable", profile["systemPrompt"])
        self.assertIn("job_token_cost_summary", profile["supportedTaskTypes"])
        self.assertIn("exactly one item", profile["systemPrompt"])
        self.assertIn("Simplified Chinese", profile["systemPrompt"])
        self.assertNotIn("{{METHODOLOGY_VERSION}}", profile["systemPrompt"])

    def test_bitfun_and_opencode_paths_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            job = base / "job"
            job.mkdir()
            bitfun = make_trial(job, "bitfun-task", adapter="bitfun", patch_rel="artifacts/model.patch")
            opencode = make_trial(job, "opencode-task", adapter="opencode", patch_rel="agent/model.patch")
            bitfun_record, bitfun_candidates = audit.extract_trial(bitfun, job)
            opencode_record, opencode_candidates = audit.extract_trial(opencode, job)

            self.assertEqual(bitfun_record["adapter"], "bitfun")
            self.assertEqual(opencode_record["adapter"], "opencode")
            self.assertTrue(bitfun_record["delivery"]["path"].endswith("artifacts/model.patch"))
            self.assertTrue(opencode_record["delivery"]["path"].endswith("agent/model.patch"))
            self.assertTrue(bitfun_record["process"]["validation_after_last_mutation"])
            self.assertTrue(opencode_record["process"]["validation_after_last_mutation"])
            self.assertNotIn("FM-05", {row["candidate_type"] for row in bitfun_candidates + opencode_candidates})
            self.assertNotIn("FM-08", {row["candidate_type"] for row in bitfun_candidates + opencode_candidates})

    def test_token_cache_is_separate_and_missing_stays_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "job"
            job.mkdir()
            present = make_trial(job, "present", include_tokens=True)
            missing = make_trial(job, "missing", include_tokens=False)
            present_record, _ = audit.extract_trial(present, job)
            missing_record, _ = audit.extract_trial(missing, job)

            self.assertEqual(present_record["tokens"]["total_tokens_excluding_cache"], 110)
            self.assertEqual(present_record["tokens"]["cache_read_tokens"], 80)
            self.assertEqual(present_record["tokens"]["status"], "complete")
            self.assertEqual(present_record["coverage"]["tokens"], "complete")
            self.assertIsNone(missing_record["tokens"]["input_tokens"])
            self.assertIsNone(missing_record["tokens"]["total_tokens_excluding_cache"])
            self.assertEqual(missing_record["tokens"]["status"], "missing")
            self.assertEqual(missing_record["coverage"]["tokens"], "absent")

    def test_result_token_ledger_aggregates_step_results_and_coverage(self) -> None:
        def context(input_tokens: int, output_tokens: int, requests: int) -> dict:
            return {
                "n_input_tokens": input_tokens,
                "n_output_tokens": output_tokens,
                "n_cache_tokens": input_tokens // 2,
                "metadata": {
                    "aeo_model_usage": {
                        "schemaVersion": "harbor-model-usage/1.3",
                        "requestCount": requests,
                        "coveredRequestCount": requests,
                        "inputTokensComplete": True,
                        "outputTokensComplete": True,
                        "collectionComplete": True,
                    }
                },
            }

        values, coverage, warnings = audit.result_token_ledger({
            "agent_result": context(100, 10, 2),
            "step_results": [
                {"agent_result": context(20, 3, 1)},
                {"ignored": True},
            ],
        })

        self.assertEqual(values["input_tokens"], 120)
        self.assertEqual(values["output_tokens"], 13)
        self.assertEqual(values["cache_read_tokens"], 60)
        self.assertEqual(coverage["status"], "complete")
        self.assertEqual(coverage["context_count"], 2)
        self.assertEqual(coverage["request_count"], 3)
        self.assertEqual(coverage["covered_request_count"], 3)
        self.assertEqual(warnings, [])

    def test_result_token_ledger_marks_incomplete_request_coverage_partial(self) -> None:
        values, coverage, warnings = audit.result_token_ledger({
            "agent_result": {
                "n_input_tokens": 100,
                "n_output_tokens": 10,
                "metadata": {"aeo_model_usage": {
                    "requestCount": 2,
                    "coveredRequestCount": 1,
                    "inputTokensComplete": True,
                    "outputTokensComplete": True,
                    "collectionComplete": True,
                }},
            }
        })

        self.assertEqual(values["input_tokens"], 100)
        self.assertEqual(coverage["status"], "partial")
        self.assertIn("incomplete or unproven", warnings[0])

    def test_result_token_ledger_rejects_unproven_zero_but_keeps_confirmed_zero(self) -> None:
        missing_values, missing_coverage, _ = audit.result_token_ledger({
            "agent_result": {"n_input_tokens": 0, "n_output_tokens": 0}
        })
        self.assertIsNone(missing_values["input_tokens"])
        self.assertEqual(missing_coverage["status"], "missing")

        zero_values, zero_coverage, warnings = audit.result_token_ledger({
            "agent_result": {
                "n_input_tokens": 0,
                "n_output_tokens": 0,
                "metadata": {"aeo_model_usage": {
                    "schemaVersion": "harbor-model-usage/1.3",
                    "requestCount": 0,
                    "coveredRequestCount": 0,
                    "excludedRequestCount": 1,
                    "inputTokensComplete": True,
                    "outputTokensComplete": True,
                    "collectionComplete": True,
                }},
            }
        })
        self.assertEqual(zero_values["input_tokens"], 0)
        self.assertEqual(zero_values["output_tokens"], 0)
        self.assertEqual(zero_coverage["status"], "complete")
        self.assertTrue(zero_coverage["confirmed_zero"])
        self.assertEqual(warnings, [])

    def test_integrity_candidates_require_tool_calls_and_are_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "job"
            job.mkdir()
            trial = make_trial(job, "integrity", extra_calls=[
                {"function_name": "bash", "arguments": {"command": "curl -H 'Authorization: Bearer top-secret-token' https://example.com/solution"}},
                {"function_name": "WebFetch", "arguments": {"url": "https://example.com/task-specific-answer.patch"}},
                {"function_name": "bash", "arguments": {"command": "OPENAI_API_KEY=another-secret pnpm install https://user:password@example.com/pkg"}},
                {"function_name": "edit", "arguments": {"filePath": "/workspace/verifier/reward.json"}},
            ])
            trajectory_path = trial / "agent" / "trajectory.json"
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            trajectory["steps"][0]["message"] += " https://github.com/example/repo/pull/1"
            trajectory["steps"][3]["observation"] = "curl: connection refused; command failed"
            dump(trajectory_path, trajectory)
            _, candidates = audit.extract_trial(trial, job)
            candidate_types = [row["candidate_type"] for row in candidates]
            rendered = json.dumps(candidates, ensure_ascii=False)

            self.assertEqual(candidate_types.count("external_access_candidate"), 2)
            self.assertIn("dependency_or_tool_fetch", candidate_types)
            self.assertIn("evaluation_artifact_mutation_candidate", candidate_types)
            access_results = {row["details"].get("access_result") for row in candidates if row["candidate_type"] == "external_access_candidate"}
            self.assertEqual(access_results, {"failure", "success"})
            self.assertTrue(all(row["methodology_version"] == "2.9.0" for row in candidates))
            self.assertNotIn("top-secret-token", rendered)
            self.assertNotIn("another-secret", rendered)
            self.assertNotIn("user:password", rendered)
            self.assertIn("<redacted>", rendered)

    def test_comparability_never_calls_checksum_mismatch_strict(self) -> None:
        left = {"task_name": "dataset/task", "task_checksum": "a", "baseline": "base", "verifier_fingerprint": "v", "prompt_fingerprint": "p"}
        right = {"task_name": "dataset/task", "task_checksum": "b", "baseline": "base", "verifier_fingerprint": "v", "prompt_fingerprint": "p"}
        grade, _ = audit.comparison_grade(left, right)
        self.assertEqual(grade, "conditional")
        right["task_checksum"] = "a"
        grade, _ = audit.comparison_grade(left, right)
        self.assertEqual(grade, "strict")
        right["verifier_fingerprint"] = "other"
        grade, _ = audit.comparison_grade(left, right)
        self.assertEqual(grade, "ineligible")

    def test_timeout_is_censored_not_oom(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "job"
            job.mkdir()
            trial = make_trial(job, "timeout", reward=0, exception="TimeoutError")
            record, candidates = audit.extract_trial(trial, job)
            self.assertTrue(record["latency"]["censored"])
            rendered = json.dumps(candidates, ensure_ascii=False).lower()
            self.assertNotIn("out of memory", rendered)

    def test_unknown_schema_degrades_without_inventing_zeroes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "job"
            root = job / "unknown"
            root.mkdir(parents=True)
            dump(root / "result.json", {"trial_name": "unknown", "task_name": "dataset/unknown"})
            dump(root / "config.json", {"agent": {"name": "custom"}})
            record, _ = audit.extract_trial(root, job)
            self.assertEqual(record["adapter"], "harbor-generic")
            self.assertEqual(record["health"], "degraded")
            self.assertEqual(record["coverage"]["trace"], "absent")
            self.assertEqual(record["coverage"]["verifier"], "absent")
            self.assertIsNone(record["tokens"]["input_tokens"])

    def test_standard_selection_is_order_independent(self) -> None:
        records = []
        for index in range(20):
            records.append({
                "trial_key": f"job/t{index:02d}", "trial": f"t{index:02d}", "task_name": f"dataset/family-{index:02d}",
                "score": {"reconciled": {"reward": 0, "f2p_failed": 1, "p2p_failed": 0}},
                "tokens": {"total_tokens_excluding_cache": index + 1}, "exception_type": None,
            })
        left = audit.single_selection(records, "standard")
        right = audit.single_selection(list(reversed(records)), "standard")
        self.assertEqual([row["left_trial_key"] for row in left], [row["left_trial_key"] for row in right])
        self.assertEqual(len(left), 12)

    def test_cli_rerun_preserves_human_files_and_redacts_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            job = base / "job"
            job.mkdir()
            make_trial(job, "task")
            output = base / "output"
            args = argparse.Namespace(inputs=[job], output=output, mode="job", depth="standard", focus="all")
            audit.run(args)
            manifest = json.loads((output / "generated" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["methodology_version"], "2.9.0")
            self.assertEqual(manifest["rule_version"], "trajectory-audit-v2")
            report = output / "report.md"
            findings = output / "adjudicated" / "findings.jsonl"
            report.write_text("human report\n", encoding="utf-8")
            findings.write_text('{"human": true}\n', encoding="utf-8")
            audit.run(args)

            self.assertEqual(report.read_text(encoding="utf-8"), "human report\n")
            self.assertEqual(findings.read_text(encoding="utf-8"), '{"human": true}\n')
            generated = "".join(path.read_text(encoding="utf-8") for path in (output / "generated").iterdir() if path.is_file())
            self.assertNotIn("super-secret-value", generated)
            self.assertNotIn("also-secret", generated)

    def test_compact_layout_has_three_files_and_preserves_human_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            job = base / "job"
            job.mkdir()
            make_trial(job, "task")
            output = base / "output"
            args = argparse.Namespace(
                inputs=[job], output=output, mode="job", depth="standard", focus="all",
                output_layout="compact",
            )
            summary = audit.run(args)
            self.assertEqual(summary["output_layout"], "compact")
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"audit.json", "findings.jsonl", "report.md"},
            )
            payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["manifest"]["output_layout"], "compact")
            self.assertEqual(len(payload["trials"]), 1)
            (output / "report.md").write_text("human report\n", encoding="utf-8")
            (output / "findings.jsonl").write_text('{"human": true}\n', encoding="utf-8")
            audit.run(args)
            self.assertEqual((output / "report.md").read_text(encoding="utf-8"), "human report\n")
            self.assertEqual((output / "findings.jsonl").read_text(encoding="utf-8"), '{"human": true}\n')

    def test_output_inside_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp) / "job"
            job.mkdir()
            make_trial(job, "task")
            args = argparse.Namespace(inputs=[job], output=job / "audit", mode="job", depth="standard", focus="all")
            with self.assertRaisesRegex(ValueError, "must not be inside"):
                audit.run(args)

    def test_trial_mode_always_selects_a_passing_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            job = base / "job"
            job.mkdir()
            trial = make_trial(job, "passing", reward=1)
            output = base / "output"
            args = argparse.Namespace(inputs=[trial], output=output, mode="auto", depth="metrics", focus="all")
            summary = audit.run(args)
            rows = list(csv_row for csv_row in (output / "generated" / "selection.csv").read_text(encoding="utf-8").splitlines() if csv_row)
            self.assertEqual(summary["mode"], "trial")
            self.assertEqual(summary["depth"], "full")
            self.assertEqual(summary["selected"], 1)
            self.assertEqual(len(rows), 2)

    def test_bootstrap_is_deterministic(self) -> None:
        first = audit.bootstrap_interval([1.0, 2.0, 3.0])
        second = audit.bootstrap_interval([1.0, 2.0, 3.0])
        self.assertEqual(first, second)

    def test_paired_stats_exclude_descriptive_and_censored_pairs(self) -> None:
        rows = [
            {
                "grade": "conditional", "outcome_quadrant": "right_only", "left_reward": 0, "right_reward": 1,
                "left_duration_sec": 10, "right_duration_sec": 8, "left_total_tokens": 100, "right_total_tokens": 90,
                "left_censored": False, "right_censored": False,
            },
            {
                "grade": "conditional", "outcome_quadrant": "both_fail", "left_reward": 0, "right_reward": 0,
                "left_duration_sec": 10, "right_duration_sec": 10, "left_total_tokens": None, "right_total_tokens": 80,
                "left_censored": True, "right_censored": False,
            },
            {
                "grade": "descriptive_only", "outcome_quadrant": "left_only", "left_reward": 1, "right_reward": 0,
                "left_duration_sec": 1, "right_duration_sec": 100, "left_total_tokens": 1, "right_total_tokens": 100,
                "left_censored": False, "right_censored": False,
            },
        ]
        stats = audit.comparison_stats(rows)
        self.assertEqual(stats["eligible_pairs"], 2)
        self.assertEqual(stats["metrics"]["duration_sec"]["n_available"], 1)
        self.assertEqual(stats["metrics"]["total_tokens"]["n_available"], 1)


if __name__ == "__main__":
    unittest.main()
