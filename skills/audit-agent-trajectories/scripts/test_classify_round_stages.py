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
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "classify_round_stages.py"
SPEC = importlib.util.spec_from_file_location("classify_round_stages", SCRIPT)
assert SPEC and SPEC.loader
stages = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stages
SPEC.loader.exec_module(stages)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def trace_fixture() -> tuple[list[dict], list[dict]]:
    rounds = [
        {
            "job": "job",
            "trial_key": "job/t",
            "task_name": "dataset/t",
            "session_id": "main",
            "actor_role": "main",
            "round_key": f"r{index}",
            "round_index": index,
        }
        for index in range(1, 11)
    ]
    calls = [
        {"round_key": "r1", "operation_tags": ["exploration"], "result_status": "success"},
        {"round_key": "r2", "operation_tags": ["verification"], "result_status": "success"},
        {"round_key": "r3", "operation_tags": ["exploration"], "result_status": "success"},
        {"round_key": "r4", "operation_tags": ["editing"], "result_status": "success"},
        {"round_key": "r5", "operation_tags": ["editing"], "result_status": "success"},
        {"round_key": "r6", "operation_tags": ["verification"], "result_status": "failure"},
        {"round_key": "r7", "operation_tags": ["editing"], "result_status": "success"},
        {"round_key": "r8", "operation_tags": ["verification"], "result_status": "success"},
        {"round_key": "r9", "operation_tags": ["verification"], "result_status": "success"},
        {"round_key": "r10", "operation_tags": ["exploration"], "result_status": "success"},
    ]
    return rounds, calls


class ClassifyRoundStagesTests(unittest.TestCase):
    def test_ebivp_boundaries_include_pre_edit_baseline(self) -> None:
        rounds, calls = trace_fixture()
        boundaries, classified = stages.project_stages(rounds, calls)
        self.assertEqual(len(boundaries), 1)
        boundary = boundaries[0]
        self.assertEqual(boundary["first_mutation_round"], 4)
        self.assertEqual(boundary["first_observed_validation_round"], 2)
        self.assertEqual(boundary["first_post_mutation_validation_round"], 6)
        self.assertEqual(boundary["stable_green_round"], 8)
        self.assertEqual(boundary["stage_string"], "E1 B2-3 I4-5 V6-8 P9-10")
        self.assertEqual(
            [row["stage"] for row in classified],
            ["E", "B", "B", "I", "I", "V", "V", "V", "P", "P"],
        )

    def test_unknown_validation_prevents_stable_green(self) -> None:
        rounds, calls = trace_fixture()
        calls[-2]["result_status"] = "unknown"
        boundaries, _ = stages.project_stages(rounds, calls)
        self.assertIsNone(boundaries[0]["stable_green_round"])
        self.assertEqual(boundaries[0]["unknown_validation_rounds"], 1)
        self.assertNotIn("P", boundaries[0]["stage_string"])

    def test_compact_output_omits_round_detail_until_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            normalized = base / "normalized"
            normalized.mkdir()
            (normalized / "manifest.json").write_text(
                json.dumps({"schema_version": "trajectory-events/1"}), encoding="utf-8"
            )
            rounds, calls = trace_fixture()
            write_jsonl(normalized / "rounds.jsonl", rounds)
            write_jsonl(normalized / "tool-calls.jsonl", calls)

            compact = base / "compact"
            stages.run(argparse.Namespace(normalized=normalized, output=compact, include_rounds=False))
            self.assertEqual(
                {path.name for path in compact.iterdir()},
                {"round-stages.json"},
            )
            self.assertFalse((compact / "staged-rounds.jsonl").exists())
            payload = json.loads((compact / "round-stages.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["boundaries"][0]["stage_string"], "E1 B2-3 I4-5 V6-8 P9-10")

            full = base / "full"
            stages.run(argparse.Namespace(normalized=normalized, output=full, include_rounds=True))
            self.assertTrue((full / "staged-rounds.jsonl").is_file())
            self.assertTrue((full / "round-stages.json").is_file())


if __name__ == "__main__":
    unittest.main()
