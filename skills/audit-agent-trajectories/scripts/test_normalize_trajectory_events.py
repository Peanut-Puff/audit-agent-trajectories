#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("normalize_trajectory_events.py")
SPEC = importlib.util.spec_from_file_location("normalize_trajectory_events", SCRIPT)
assert SPEC and SPEC.loader
normalize = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = normalize
SPEC.loader.exec_module(normalize)


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def result_payload(name: str) -> dict:
    return {
        "trial_name": name,
        "task_name": f"dataset/{name}",
        "task_checksum": f"checksum-{name}",
    }


def bitfun_agent_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        root = "agent/bitfun/sessions/main"
        bundle.writestr(f"{root}/metadata.json", json.dumps({
            "sessionId": "main",
            "sessionKind": "standard",
            "sessionName": "Primary",
            "agentType": "agentic",
        }))
        bundle.writestr(f"{root}/request-traces/request-000001.json", json.dumps({
            "trace_id": "trace-1",
            "turn_id": "turn-1",
            "request": {"body": {"messages": []}},
            "response": {
                "kind": "completed",
                "usage": {"promptTokenCount": 10, "candidatesTokenCount": 2, "cachedContentTokenCount": 4},
                "tool_calls": [{
                    "tool_id": "call-1",
                    "tool_name": "ExecCommand",
                    "arguments": {"cmd": "go test ./..."},
                    "is_error": False,
                }],
            },
        }))
        bundle.writestr(f"{root}/request-traces/request-000002.json", json.dumps({
            "trace_id": "trace-2",
            "turn_id": "turn-2",
            "request": {"body": {"messages": [{
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "Process exited with code 1\nsecret output",
            }]}},
            "response": {
                "kind": "completed",
                "tool_calls": [{
                    "tool_id": "call-2",
                    "tool_name": "Edit",
                    "arguments": {"file_path": "/app/src/code.go", "new_string": "secret source"},
                    "is_error": False,
                }],
            },
        }))
    return output.getvalue()


def opencode_agent_zip() -> bytes:
    events = [
        {"type": "step_start", "sessionID": "session", "part": {"messageID": "m1"}},
        {
            "type": "tool_use",
            "sessionID": "session",
            "part": {
                "messageID": "m1",
                "id": "c1",
                "tool": "shell",
                "state": {
                    "status": "completed",
                    "input": {"command": "rg pattern src"},
                    "output": "private result",
                    "metadata": {"metadata": {"exit": 0}},
                },
            },
        },
        {
            "type": "step_finish",
            "sessionID": "session",
            "part": {
                "messageID": "m1",
                "tokens": {"input": 7, "output": 3, "reasoning": 1, "cache": {"read": 5, "write": 0}},
            },
        },
    ]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("agent/opencode-v2.log", "\n".join(json.dumps(item) for item in events) + "\ninvalid\n")
    return output.getvalue()


class NormalizeTrajectoryEventsTests(unittest.TestCase):
    def test_operation_tags_are_semantic_and_multi_label(self) -> None:
        self.assertEqual(normalize.operation_tags("Read", {"file_path": "a.py"}), ["exploration"])
        self.assertEqual(
            normalize.operation_tags("ExecCommand", {"cmd": "sed -i s/a/b/ a.py && pytest -q"}),
            ["editing", "verification"],
        )
        self.assertEqual(normalize.operation_tags("WebFetch", {"url": "https://example.test"}), ["exploration"])
        self.assertEqual(normalize.operation_tags("WriteStdin", {"session_id": "p"}), [])

    def test_bitfun_bundle_links_tool_result_without_copying_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job" / "trial"
            root.mkdir(parents=True)
            dump(root / "result.json", result_payload("demo"))
            (root / "agent.zip").write_bytes(bitfun_agent_zip())
            trial, internal_rounds, warnings = normalize.analyze_trial_directory(root, "job")
            rounds, calls = normalize.finalize_records(internal_rounds)

            self.assertEqual(warnings, [])
            self.assertEqual(trial["adapter"], "bitfun")
            self.assertEqual(len(rounds), 2)
            self.assertEqual(rounds[0]["input_tokens"], 10)
            self.assertEqual(calls[0]["operation_tags"], ["verification"])
            self.assertEqual(calls[0]["result_status"], "failure")
            self.assertEqual(calls[1]["operation_tags"], ["editing"])
            rendered = json.dumps({"rounds": rounds, "calls": calls})
            self.assertNotIn("go test", rendered)
            self.assertNotIn("secret", rendered)
            self.assertNotIn("/app/src/code.go", rendered)

    def test_opencode_bundle_preserves_usage_and_skips_malformed_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job" / "trial"
            root.mkdir(parents=True)
            dump(root / "result.json", result_payload("demo"))
            (root / "agent.zip").write_bytes(opencode_agent_zip())
            trial, internal_rounds, warnings = normalize.analyze_trial_directory(root, "job")
            rounds, calls = normalize.finalize_records(internal_rounds)

            self.assertEqual(trial["adapter"], "opencode")
            self.assertIn("skipped malformed OpenCode log lines=1", warnings)
            self.assertEqual(rounds[0]["input_tokens"], 7)
            self.assertEqual(rounds[0]["cache_read_tokens"], 5)
            self.assertEqual(calls[0]["operation_tags"], ["exploration"])
            self.assertEqual(calls[0]["result_status"], "success")

    def test_case_log_zip_is_read_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive = base / "run-case-logs.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                prefix = "cases/demo/repeat-001/"
                outer.writestr(f"{prefix}result.json", json.dumps(result_payload("demo")))
                outer.writestr(f"{prefix}agent.zip", bitfun_agent_zip())
            output = base / "normalized"
            summary = normalize.run(argparse.Namespace(inputs=[archive], output=output, output_level="compact"))

            self.assertEqual(summary["trials"], 1)
            self.assertEqual(summary["rounds"], 2)
            self.assertEqual(summary["tool_calls"], 2)
            self.assertTrue((output / "trajectory-events.jsonl").is_file())
            self.assertTrue((output / "summary.json").is_file())
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"summary.json", "trajectory-events.jsonl"},
            )
            self.assertFalse((output / "tool-calls.csv").exists())
            self.assertFalse((output / "trials.jsonl").exists())
            first_line = (output / "trajectory-events.jsonl").read_text(encoding="utf-8").splitlines()[0]
            manifest = json.loads(first_line)["data"]
            self.assertEqual(manifest["schema_version"], "trajectory-events/1")

            full_output = base / "full"
            normalize.run(argparse.Namespace(inputs=[archive], output=full_output, output_level="full"))
            self.assertTrue((full_output / "tool-calls.csv").is_file())
            self.assertTrue((full_output / "trials.jsonl").is_file())

    def test_normalized_trajectory_and_subagent_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job" / "trial"
            root.mkdir(parents=True)
            dump(root / "result.json", result_payload("demo"))
            dump(root / "agent" / "trajectory.json", {
                "agent": {"name": "generic"},
                "rounds": [{"round_id": "main-1"}],
                "steps": [{
                    "source": "agent",
                    "round_id": "main-1",
                    "tool_calls": [{"function_name": "Read", "arguments": {"path": "a.py"}}],
                    "tool_status": "completed",
                    "observation": "contents",
                }],
                "subagent_trajectories": [{
                    "metadata": {"sessionId": "sub-1", "sessionKind": "subagent", "agentType": "review"},
                    "trajectory": {
                        "rounds": [{"round_id": "sub-round"}],
                        "steps": [{
                            "source": "agent",
                            "round_id": "sub-round",
                            "tool_calls": [{"function_name": "Grep", "arguments": {"pattern": "x"}}],
                            "tool_status": "completed",
                            "observation": "match",
                        }],
                    },
                }],
            })
            _, internal_rounds, _ = normalize.analyze_trial_directory(root, "job")
            rounds, _ = normalize.finalize_records(internal_rounds)
            self.assertEqual(len(rounds), 2)
            self.assertEqual(rounds[0]["actor_role"], "main")
            self.assertEqual(rounds[1]["actor_role"], "subagent")
            self.assertEqual(rounds[1]["agent_type"], "review")

    def test_output_inside_directory_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job" / "trial"
            root.mkdir(parents=True)
            dump(root / "result.json", result_payload("demo"))
            (root / "agent.zip").write_bytes(bitfun_agent_zip())
            with self.assertRaisesRegex(ValueError, "must not be inside"):
                normalize.run(argparse.Namespace(inputs=[root], output=root / "normalized"))


if __name__ == "__main__":
    unittest.main()
