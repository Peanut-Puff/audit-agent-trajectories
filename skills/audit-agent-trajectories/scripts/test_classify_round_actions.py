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
SCRIPT = Path(__file__).with_name("classify_round_actions.py")
SPEC = importlib.util.spec_from_file_location("classify_round_actions", SCRIPT)
assert SPEC and SPEC.loader
actions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = actions
SPEC.loader.exec_module(actions)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class ClassifyRoundActionsTests(unittest.TestCase):
    def test_priority_and_coarse_categories_are_mutually_exclusive(self) -> None:
        rounds = [
            {"job": "job", "trial_key": "job/t", "round_key": f"r{index}"}
            for index in range(1, 7)
        ]
        calls = [
            {"round_key": "r1", "operation_tags": ["exploration"]},
            {"round_key": "r2", "operation_tags": ["editing"]},
            {"round_key": "r3", "operation_tags": ["verification"]},
            {"round_key": "r4", "operation_tags": ["editing", "verification"]},
            {"round_key": "r5", "operation_tags": []},
        ]
        rows = actions.classify_rows(rounds, calls)
        self.assertEqual(
            [row["action"] for row in rows],
            ["exploration", "editing", "verification", "verification", "other", "other"],
        )
        views = actions.action_views(rows)
        self.assertEqual(views["jobs"]["job"]["rounds"], 6)
        self.assertEqual(views["jobs"]["job"]["actions"], {
            "exploration": 1,
            "editing": 1,
            "verification": 2,
            "other": 2,
        })

    def test_all_label_combinations_match_bitfun_priority(self) -> None:
        combinations = (
            ("exploration",),
            ("editing",),
            ("verification",),
            ("exploration", "editing"),
            ("exploration", "verification"),
            ("editing", "verification"),
            ("exploration", "editing", "verification"),
            (),
        )
        counts = {"exploration": 0, "editing": 0, "verification": 0, "other": 0}
        for labels in combinations:
            counts[actions.classify(set(labels), bool(labels))] += 1
        self.assertEqual(
            counts,
            {"exploration": 1, "editing": 2, "verification": 4, "other": 1},
        )

    def test_compact_output_omits_round_detail_until_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            normalized = base / "normalized"
            normalized.mkdir()
            write_jsonl(normalized / "trajectory-events.jsonl", [
                {"record_type": "manifest", "data": {"schema_version": "trajectory-events/1"}},
                {"record_type": "round", "job": "job", "trial_key": "job/t", "round_key": "r1"},
                {
                    "record_type": "tool_call", "job": "job", "trial_key": "job/t",
                    "round_key": "r1", "operation_tags": ["exploration"],
                },
            ])

            compact = base / "compact"
            actions.run(argparse.Namespace(normalized=normalized, output=compact, include_rounds=False))
            self.assertEqual(
                {path.name for path in compact.iterdir()},
                {"round-actions.json"},
            )
            self.assertFalse((compact / "classified-rounds.jsonl").exists())

            full = base / "full"
            actions.run(argparse.Namespace(normalized=normalized, output=full, include_rounds=True))
            self.assertTrue((full / "classified-rounds.jsonl").is_file())
            self.assertTrue((full / "round-actions.json").is_file())


if __name__ == "__main__":
    unittest.main()
