#!/usr/bin/env python3
"""Synthetic contract and evidence-boundary regression tests for HTML presentation."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.dont_write_bytecode = True
import render_audit_html as render
from test_audit_trajectories import audit, dump, make_trial


def payload(key: str = "left/task", depth: str = "full") -> dict:
    return {
        "source": "/synthetic/audit", "manifest": {"schema_version": 1, "depth": depth, "methodology_version": audit.METHODOLOGY_VERSION},
        "trials": [{"trial_key": key, "task_name": "task", "adapter": "bitfun", "baseline": "b", "task_checksum": "c",
                    "verifier_fingerprint": "v", "health": "behavior_unverified", "coverage": {"tokens": "complete", "verifier": "absent"},
                    "tokens": {"input_tokens": 50, "status": "complete", "coverage": {"authoritative_source": "result_agent_results"}},
                    "score": {"raw": {"reward": None}, "reconciled": {"reward": None}},
                    "latency": {"duration_sec": 10, "censored": False}, "provenance": {}}],
        "candidates": [], "findings": [],
    }


def normalized_rounds() -> list[dict]:
    return [{"trial_key": "left/task", "session_id": "main", "round_key": f"r{i}", "round_index": i,
             "input_tokens": value, "source": "/synthetic/events.json"} for i, value in enumerate((10, None, 30), 1)]


def annotations() -> dict:
    return {"schema_version": "trial-presentation/1", "trials": {"left/task": {
        "input_token_semantics": "includes_cache", "evidence_refs": ["/synthetic/source#time"],
        "round_elapsed_sec": {"r1": 1, "r2": 2, "r3": 3},
        "semantic_stages": [{"title": "实现接通", "goal": "bounded-goal-marker", "round_keys": ["r1"],
                             "annotation_method": "manual", "evidence_refs": ["r1"], "uncertainty": "局部样本"}]}}}


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.external: list[str] = []
        self.scripts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        row = dict(attrs)
        if row.get("id"):
            self.ids.append(row["id"])
        if row.get("src") or row.get("href", "").startswith("http"):
            self.external.append(str(row))
        if tag == "script":
            self.scripts += 1


class HtmlPresentationTests(unittest.TestCase):
    def test_unknown_result_stays_unknown_and_no_failure_cause_is_generated(self) -> None:
        view = render.build_view([payload()])
        trial = view["trials"][0]
        self.assertEqual(trial["outcome"], "未知")
        self.assertEqual(trial["health"], "behavior_unverified")
        self.assertEqual(trial["findings"], [])
        self.assertIsNone(next(m["value"] for m in trial["metrics"] if m["label"] == "报告费用"))

    def test_missing_rounds_are_not_zeroed_and_auxiliary_rounds_reconcile(self) -> None:
        view = render.build_view([payload()], annotations(), normalized_rounds())
        trial = view["trials"][0]
        points = trial["curves"][0]["points"]
        self.assertEqual([p["cumulative"] for p in points], [10, None, 40])
        self.assertTrue(points[-1]["gap"])
        self.assertEqual(trial["reconciliation"]["ledger_minus_observed"], 10)
        self.assertEqual(trial["reconciliation"]["unassigned_or_auxiliary_rounds"], 2)
        self.assertEqual(trial["semantic_stages"][0]["input_observed"], 10)

    def test_all_five_curve_metrics_keep_missing_and_cache_semantics_separate(self) -> None:
        rounds = normalized_rounds()
        for row, output, reasoning, cached in zip(rounds, (4, None, 6), (0, 2, None), (3, 4, 40)):
            row.update(output_tokens=output, reasoning_tokens=reasoning, cache_read_tokens=cached)
        view = render.build_view([payload()], annotations(), rounds)
        points = view["trials"][0]["curves"][0]["points"]
        self.assertEqual([p["input"] for p in points], [10, None, 30])
        self.assertEqual([p["cumulative"] for p in points], [10, None, 40])
        self.assertEqual([p["cumulative_output"] for p in points], [4, None, 10])
        self.assertEqual([p["cumulative_reasoning"] for p in points], [0, 2, None])
        self.assertEqual([p["cumulative_uncached"] for p in points], [7, None, None])
        self.assertTrue(points[-1]["gaps"]["output"])
        self.assertFalse(points[1]["gaps"]["reasoning"])
        data = annotations()
        data["trials"]["left/task"]["input_token_semantics"] = "unknown"
        points = render.build_view([payload()], data, rounds)["trials"][0]["curves"][0]["points"]
        self.assertTrue(all(p["cumulative_uncached"] is None for p in points))
        data["trials"]["left/task"]["input_token_semantics"] = "excludes_cache"
        points = render.build_view([payload()], data, rounds)["trials"][0]["curves"][0]["points"]
        self.assertEqual([p["cumulative_uncached"] for p in points], [10, None, 40])

    def test_metrics_suppresses_behavior_from_both_page_and_embedded_evidence(self) -> None:
        source = payload(depth="metrics")
        source["findings"] = [{"trial_key": "left/task", "adjudication": "confirmed", "summary": "hidden-cause-marker"}]
        view = render.build_view([source], annotations(), normalized_rounds())
        self.assertNotIn("hidden-cause-marker", json.dumps(view))
        self.assertNotIn("bounded-goal-marker", json.dumps(view))
        self.assertEqual(view["trials"][0]["suppressed_findings"], 1)

    def test_overlapping_unknown_and_decreasing_time_annotations_are_rejected(self) -> None:
        for mutation in ("overlap", "unknown", "time", "no_source"):
            data = annotations()
            trial = data["trials"]["left/task"]
            if mutation == "overlap":
                trial["semantic_stages"].append(copy.deepcopy(trial["semantic_stages"][0]))
            elif mutation == "unknown":
                trial["semantic_stages"][0]["round_keys"] = ["missing"]
            elif mutation == "time":
                trial["round_elapsed_sec"]["r3"] = 0
            else:
                trial.pop("evidence_refs")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                render.build_view([payload()], data, normalized_rounds())

    def test_pair_excludes_unknown_outcomes_ineligible_tokens_and_censored_duration(self) -> None:
        left, right = payload(), payload("right/task")
        right["trials"][0]["latency"]["censored"] = True
        view = render.build_view([left, right])
        self.assertEqual(view["pair"]["grade"], "strict")
        self.assertEqual(view["pair"]["quadrant"], "未知或不合格")
        self.assertTrue(all(row["n_available"] == 0 for row in view["pair"]["metrics"]))
        data = {"schema_version": "trial-presentation/1", "trials": {key: {"input_token_semantics": "includes_cache"} for key in ("left/task", "right/task")}}
        view = render.build_view([left, right], data)
        self.assertEqual(view["pair"]["metrics"][0]["delta"], 0)
        right["trials"][0]["baseline"] = "conflict"
        view = render.build_view([left, right], data)
        self.assertEqual(view["pair"]["grade"], "ineligible")
        self.assertIsNone(view["pair"]["metrics"][0]["delta"])

    def test_stage_alignment_preserves_identity_and_rejects_ambiguous_or_invalid_measurements(self) -> None:
        data = annotations()
        stage = data["trials"]["left/task"]["semantic_stages"][0]
        stage["alignment_key"] = "implementation"
        stage["duration_sec"] = 0
        view = render.build_view([payload()], data, normalized_rounds())
        item = view["trials"][0]["semantic_stages"][0]
        self.assertEqual(item["alignment_key"], "implementation")
        self.assertEqual(item["duration_sec"], 0)
        for value in (-1, "10", float("nan")):
            stage["duration_sec"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                render.build_view([payload()], data, normalized_rounds())
        stage["duration_sec"] = None
        duplicate = copy.deepcopy(stage)
        duplicate["round_keys"] = ["r3"]
        data["trials"]["left/task"]["semantic_stages"].append(duplicate)
        with self.assertRaises(ValueError):
            render.build_view([payload()], data, normalized_rounds())

    def test_job_and_duplicate_identity_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render.build_view([payload(), payload()])
        source = payload()
        source["trials"] *= 3
        with self.assertRaises(ValueError):
            render.build_view([source])

    def test_job_overview_preserves_missing_outcomes_and_excludes_invalid_pair_metrics(self) -> None:
        sources = []
        annotations_data = {"schema_version": "trial-presentation/1", "trials": {}}
        for job in ("left", "right"):
            source = payload(f"{job}/task")
            source["manifest"].update(mode="job", focus=["tokens"])
            record = source["trials"][0]
            record.update(job=job, trial="task", task_name="task", job_root=f"/synthetic/{job}")
            annotations_data["trials"][record["trial_key"]] = {"input_token_semantics": "includes_cache"}
            sources.append(source)
        sources[1]["trials"][0]["latency"]["censored"] = True
        view = render.build_job_view(sources, annotations_data)
        self.assertEqual(view["kind"], "job")
        self.assertEqual(len(view["jobs"]), 2)
        self.assertEqual(view["trials"][0]["outcome"], "未知")
        pair = view["pairs"][0]
        self.assertEqual(pair["grade"], "strict")
        self.assertEqual(pair["outcome"], "未知或不合格")
        by_label = {item["label"]: item for item in pair["metrics"]}
        self.assertEqual(by_label["完成耗时"]["n_available"], 0)
        self.assertEqual(by_label["输入 token"]["delta"], 0)
        self.assertIsNone(by_label["模型轮次"]["delta"])
        sources[1]["trials"][0]["baseline"] = "different"
        view = render.build_job_view(sources, annotations_data)
        self.assertEqual(view["pairs"][0]["grade"], "ineligible")
        self.assertTrue(all(item["delta"] is None for item in view["pairs"][0]["metrics"]))

    def test_job_index_omits_raw_requests_and_metrics_behavior(self) -> None:
        source = payload(depth="metrics")
        source["manifest"]["mode"] = "job"
        source["trials"][0].update(job="left", trial="task", reasoning="private-marker")
        source["findings"] = [{"trial_key": "left/task", "summary": "private-finding-marker"}]
        view = render.build_job_view([source], annotations(), normalized_rounds())
        self.assertEqual(view["trials"][0]["metrics"]["rounds"], 3)
        self.assertNotIn("private-marker", json.dumps(view))
        self.assertNotIn("private-finding-marker", json.dumps(view))
        self.assertNotIn("bounded-goal-marker", json.dumps(view))
        self.assertNotIn("curves", view["trials"][0])

    def test_single_and_paired_jobs_generate_valid_static_details_in_both_layouts(self) -> None:
        for layout in ("compact", "expanded"):
            for paired in (False, True):
                with self.subTest(layout=layout, paired=paired), tempfile.TemporaryDirectory() as temp:
                    base = Path(temp)
                    inputs = []
                    for name in (("left", "right") if paired else ("left",)):
                        job = base / name
                        for task in ("one", "two", "three"):
                            make_trial(job, task)
                        inputs.append(job)
                    out = base / "audit"
                    args = argparse.Namespace(inputs=inputs, output=out, mode="paired" if paired else "job",
                                              depth="standard", focus="all", output_layout=layout, html=True)
                    audit.run(args)
                    document = (out / "report.html").read_text()
                    view = json.loads(document.split('<script id="audit-data" type="application/json">')[1].split('</script>')[0])
                    self.assertEqual(view["kind"], "job")
                    self.assertEqual(len(view["trials"]), 6 if paired else 3)
                    details = out / view["details_dir"]
                    for trial in view["trials"]:
                        page = details / trial["detail"]
                        self.assertTrue(page.is_file())
                        self.assertIn('"overview_href": "../report.html"', page.read_text())
                    for pair in view["pairs"]:
                        self.assertTrue((details / pair["detail"]).is_file())
                    report_before = (out / "report.md").read_bytes()
                    audit.run(args)
                    self.assertEqual(report_before, (out / "report.md").read_bytes())

    def test_no_remote_assets_or_script_injection_and_credentials_are_masked(self) -> None:
        source = payload()
        source["findings"] = [{"trial_key": "left/task", "adjudication": "confirmed", "finding_id": "f1",
                               "summary": '</script><script>alert("attack")</script> api_key=supersecretvalue',
                               "reasoning": "raw-private-reasoning-marker"}]
        document = render.render_document(render.build_view([source]))
        parser = Parser()
        parser.feed(document)
        self.assertEqual(parser.scripts, 2)
        self.assertEqual(parser.external, [])
        self.assertNotIn("supersecretvalue", document)
        self.assertNotIn("raw-private-reasoning-marker", document)
        self.assertNotIn('</script><script>alert', document)
        self.assertIn("connect-src 'none'", document)

    def test_html_opt_in_and_rerun_preserve_manual_files_and_raw_input(self) -> None:
        for layout in ("compact", "expanded"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                trial = make_trial(base / "job", "task")
                raw_before = {str(p): p.read_bytes() for p in trial.rglob("*") if p.is_file()}
                out = base / "audit"
                args = argparse.Namespace(inputs=[trial], output=out, mode="trial", depth="full", focus="all", output_layout=layout)
                audit.run(args)
                self.assertFalse((out / "report.html").exists())
                findings = out / "findings.jsonl" if layout == "compact" else out / "adjudicated" / "findings.jsonl"
                findings.write_text('{"trial_key":"job/task","human":true}\n', encoding="utf-8")
                (out / "report.md").write_text("manual-report", encoding="utf-8")
                args.html = True
                audit.run(args)
                self.assertTrue((out / "report.html").is_file())
                first = (out / "report.html").read_text(encoding="utf-8")
                audit.run(args)
                self.assertEqual(findings.read_text(), '{"trial_key":"job/task","human":true}\n')
                self.assertEqual((out / "report.md").read_text(), "manual-report")
                self.assertIn("trial-html/1", first)
                self.assertEqual(raw_before, {str(p): p.read_bytes() for p in trial.rglob("*") if p.is_file()})
                with self.assertRaises(ValueError):
                    render.run(argparse.Namespace(inputs=[out], output=trial / "report.html"))

    def test_invalid_findings_is_reported_and_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            source = payload()
            dump(out / "audit.json", source)
            findings = out / "findings.jsonl"
            findings.write_text("{broken}\n")
            with self.assertRaises(ValueError):
                render.load_audit(out)
            self.assertEqual(findings.read_text(), "{broken}\n")

    def test_layout_switch_uses_current_output_and_ambiguous_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            trial = make_trial(base / "job", "task")
            out = base / "audit"
            args = argparse.Namespace(inputs=[trial], output=out, mode="trial", depth="full", focus="all", output_layout="compact", html=True)
            audit.run(args)
            args.output_layout = "expanded"
            result = json.loads((trial / "result.json").read_text())
            result["agent_result"]["n_input_tokens"] = 333
            dump(trial / "result.json", result)
            audit.run(args)
            current = render.load_audit(out / "generated" / "manifest.json")
            self.assertEqual(current["trials"][0]["tokens"]["input_tokens"], 333)
            document = (out / "report.html").read_text()
            embedded = json.loads(document.split('<script id="audit-data" type="application/json">')[1].split('</script>')[0])
            self.assertEqual(embedded["trials"][0]["tokens"]["input_tokens"], 333)
            with self.assertRaises(ValueError):
                render.load_audit(out)


if __name__ == "__main__":
    unittest.main()
