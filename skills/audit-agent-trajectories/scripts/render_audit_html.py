#!/usr/bin/env python3
"""Render Trial or Job audits as offline HTML; Python standard library only."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import math
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
import audit_trajectories as audit
import classify_round_actions as actions
import classify_round_stages as stages


PRESENTATION_VERSION = "trial-html/1"
ANNOTATION_VERSION = "trial-presentation/1"
ASSETS = Path(__file__).resolve().parents[1] / "assets" / "html"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError(f"cannot read JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_audit(source: Path) -> dict[str, Any]:
    source = source.resolve()
    if source.is_dir() and (source / "audit.json").exists() and (source / "generated" / "manifest.json").exists():
        raise ValueError(f"mixed audit layouts; pass audit.json or generated/manifest.json explicitly: {source}")
    expanded_manifest = source.is_file() and source.name == "manifest.json" and source.parent.name == "generated"
    compact = source / "audit.json" if source.is_dir() else source
    if compact.is_file() and not expanded_manifest:
        payload = read_json(compact)
        findings = compact.parent / "findings.jsonl"
    else:
        generated = source.parent if expanded_manifest else source / "generated"
        payload = {
            "manifest": read_json(generated / "manifest.json"),
            "trials": actions.load_jsonl(generated / "trials.jsonl"),
            "candidates": actions.load_jsonl(generated / "candidates.jsonl"),
        }
        selection_path = generated / "selection.csv"
        if selection_path.is_file():
            with selection_path.open(encoding="utf-8", newline="") as handle:
                payload["selection"] = list(csv.DictReader(handle))
        findings = generated.parent / "adjudicated" / "findings.jsonl"
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != audit.SCHEMA_VERSION:
        raise ValueError(f"unsupported audit schema: {source}")
    if manifest.get("depth") not in {"metrics", "standard", "full"}:
        raise ValueError(f"unknown audit depth: {source}")
    records = payload.get("trials")
    if not isinstance(records, list) or not records or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"expected nonempty audit.trials: {source}")
    payload["findings"] = actions.load_jsonl(findings) if findings.is_file() else []
    payload["source"] = str(source)
    return payload


def numeric(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def clean(value: Any) -> Any:
    """Bound and redact all displayed strings, including human annotations."""
    if isinstance(value, str):
        return audit.redact_text(value, 1200)
    if isinstance(value, dict):
        return {audit.redact_text(str(key), 200): clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def select_fields(row: dict[str, Any], fields: str) -> dict[str, Any]:
    return {key: row.get(key) for key in fields.split()}


def outcome(record: dict[str, Any]) -> str:
    reward = audit.nested(record, "score", "reconciled", "reward")
    return "未知" if not numeric(reward) else "通过" if reward > 0 else "失败"


class Evidence:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, title: str, value: Any, source: Any, limitation: str = "") -> str:
        key = f"e{len(self.rows) + 1}"
        self.rows.append({"id": key, "title": title, "facts": value, "source": source, "limitation": limitation})
        return key


def metric(label: str, value: Any, source: Any, evidence: Evidence, unit: str = "", note: str = "") -> dict[str, Any]:
    present = value is not None
    ref = evidence.add(label, {"value": value, "unit": unit, "valid": int(present), "missing": int(not present), "denominator": 1}, source, note)
    return {"label": label, "value": value, "unit": unit, "ref": ref, "note": note, "valid": int(present)}


def summarize_usage(rows: list[dict[str, Any]], semantics: str) -> dict[str, Any]:
    """Observed subtotals only. Missing metrics remain null, never synthetic zero."""
    summary: dict[str, Any] = {}
    fields = {"input": "input_tokens", "output": "output_tokens", "reasoning": "reasoning_tokens", "cache": "cache_read_tokens"}
    for label, field in fields.items():
        values = [row[field] for row in rows if numeric(row.get(field)) and row[field] >= 0]
        summary[label + "_observed"] = sum(values) if values else None
        summary[label + "_missing"] = len(rows) - len(values)
    fresh = []
    for row in rows:
        value, cached = row.get("input_tokens"), row.get("cache_read_tokens")
        if not numeric(value) or value < 0:
            continue
        if semantics == "excludes_cache":
            fresh.append(value)
        elif semantics == "includes_cache" and numeric(cached) and 0 <= cached <= value:
            fresh.append(value - cached)
    summary.update(uncached_observed=sum(fresh) if fresh else None, uncached_missing=len(rows) - len(fresh))
    return summary


def prepare_trial(payload: dict[str, Any], record: dict[str, Any], annotation: dict[str, Any],
                  rounds: list[dict[str, Any]], calls: list[dict[str, Any]], evidence: Evidence) -> dict[str, Any]:
    key = record["trial_key"]
    if not isinstance(annotation, dict):
        raise ValueError(f"annotation must be an object: {key}")
    manifest = payload["manifest"]
    depth = manifest.get("depth", "unknown")
    prov = record.get("provenance") or {}
    tokens = record.get("tokens") or {}
    latency = record.get("latency") or {}
    process = record.get("process") or {}
    score = record.get("score") or {}
    source = {"audit": payload["source"], "trial_key": key}
    own_rounds = [row for row in rounds if row.get("trial_key") == key]
    own_calls = [row for row in calls if row.get("trial_key") == key]
    boundaries, classified = stages.project_stages(own_rounds, own_calls)
    semantics = annotation.get("input_token_semantics", "unknown")
    if semantics not in {"includes_cache", "excludes_cache", "unknown"}:
        raise ValueError(f"invalid input_token_semantics for {key}")
    round_keys = [row["round_key"] for row in own_rounds]
    if len(round_keys) != len(set(round_keys)):
        raise ValueError(f"duplicate normalized round_key for {key}")
    elapsed = annotation.get("round_elapsed_sec") or {}
    if not isinstance(elapsed, dict) or any(k not in round_keys or not numeric(v) or v < 0 for k, v in elapsed.items()):
        raise ValueError(f"round_elapsed_sec must map known round keys to nonnegative seconds: {key}")
    if elapsed and not annotation.get("evidence_refs"):
        raise ValueError(f"request times require evidence_refs: {key}")
    if not isinstance(annotation.get("semantic_stages", []), list):
        raise ValueError(f"semantic_stages must be an array: {key}")
    curves = []
    points_by_key: dict[str, dict[str, Any]] = {}
    # Preserve session boundaries: sorting unrelated sessions into one ordinal would imply chronology.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in classified:
        grouped.setdefault(str(row.get("session_id")), []).append(row)
    for session, rows in grouped.items():
        totals = {field: 0 for field in ("input", "output", "reasoning", "uncached")}
        gaps = {field: False for field in totals}
        last_time = -1.0
        points = []
        for row in sorted(rows, key=lambda item: item.get("round_index", 0)):
            usage = {field: row.get(field) if numeric(row.get(field)) and row[field] >= 0 else None
                     for field in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens")}
            value, cached = usage["input_tokens"], usage["cache_read_tokens"]
            uncached = (value - cached if semantics == "includes_cache" and value is not None
                        and cached is not None and cached <= value else
                        value if semantics == "excludes_cache" else None)
            values = {"input": value, "output": usage["output_tokens"],
                      "reasoning": usage["reasoning_tokens"], "uncached": uncached}
            cumulative = {}
            for field, observed in values.items():
                gaps[field] = gaps[field] or observed is None
                if observed is not None:
                    totals[field] += observed
                cumulative[field] = totals[field] if observed is not None else None
            time = elapsed.get(row["round_key"])
            if time is not None and time < last_time:
                raise ValueError(f"round_elapsed_sec decreases within session {session}: {key}")
            if time is not None:
                last_time = time
            ref = evidence.add(f"请求 {row.get('round_index')} / {session}",
                               {**select_fields(row, "round_key round_id round_index session_id stage action"), **usage,
                                "elapsed_sec": time, "input_token_semantics": semantics, "uncached_input_tokens": uncached},
                               {"events": row.get("source"), "annotation_sources": annotation.get("evidence_refs")},
                               "归一化请求的报告输入；未声明缓存关系时不能等同完整上下文。时间来自独立标注。")
            points.append({"n": row.get("round_index"), "input": value, "cumulative": cumulative["input"],
                           "cumulative_output": cumulative["output"], "cumulative_reasoning": cumulative["reasoning"],
                           "cumulative_uncached": cumulative["uncached"], "usage": {**values},
                           "elapsed": time, "ref": ref, "gap": gaps["input"], "gaps": gaps.copy()})
            points_by_key[row["round_key"]] = points[-1]
        curves.append({"session": session, "points": points})

    assigned: set[str] = set()
    alignment_keys: set[str] = set()
    stage_ids: set[str] = set()
    session_positions = {session: {row["round_key"]: index for index, row in enumerate(sorted(rows, key=lambda r: r.get("round_index", 0)))}
                         for session, rows in grouped.items()}
    last_position: dict[str, int] = {}
    semantic = []
    for phase_index, phase in enumerate(annotation.get("semantic_stages", []), 1):
        if not isinstance(phase, dict) or not isinstance(phase.get("round_keys"), list) or not phase["round_keys"]:
            raise ValueError(f"semantic stage requires nonempty round_keys: {key}")
        members = phase["round_keys"]
        if len(set(members)) != len(members) or set(members) - set(round_keys) or assigned.intersection(members):
            raise ValueError(f"unknown or overlapping semantic stage rounds: {key}")
        assigned.update(members)
        rows = [row for row in own_rounds if row["round_key"] in members]
        sessions = {str(row.get("session_id")) for row in rows}
        if len(sessions) != 1:
            raise ValueError(f"semantic stage cannot join sessions: {key}")
        session = next(iter(sessions))
        rows.sort(key=lambda r: session_positions[session][r["round_key"]])
        positions = [session_positions[session][row["round_key"]] for row in rows]
        if positions != list(range(positions[0], positions[-1] + 1)) or positions[0] <= last_position.get(session, -1):
            raise ValueError(f"semantic stages must be contiguous and chronological within session: {key}")
        last_position[session] = positions[-1]
        stage_id = phase.get("stage_id", f"s{phase_index}")
        if not isinstance(stage_id, str) or not stage_id.strip() or stage_id in stage_ids:
            raise ValueError(f"semantic stage_id must be unique and nonempty: {key}")
        stage_ids.add(stage_id)
        item = select_fields(phase, "title alignment_key goal actions result duration_sec anomalies evidence_refs annotation_method uncertainty")
        alignment_key = phase.get("alignment_key")
        if alignment_key is not None:
            if not isinstance(alignment_key, str) or not alignment_key.strip() or alignment_key in alignment_keys:
                raise ValueError(f"semantic alignment_key must be a unique nonempty string: {key}")
            alignment_keys.add(alignment_key)
        if phase.get("duration_sec") is not None and (not numeric(phase["duration_sec"]) or phase["duration_sec"] < 0):
            raise ValueError(f"semantic duration_sec must be nonnegative or null: {key}")
        if not item.get("annotation_method") or not item.get("evidence_refs"):
            raise ValueError(f"semantic stage requires annotation_method and evidence_refs: {key}")
        item.update({"stage_id": stage_id, "session_id": session,
                     "start_round": rows[0].get("round_index"), "end_round": rows[-1].get("round_index"),
                     "rounds": len(rows), "tool_calls": sum(row.get("tool_call_count") or 0 for row in rows),
                     **summarize_usage(rows, semantics)})
        if depth != "metrics":
            item["ref"] = evidence.add(f"语义阶段 / {phase.get('title')}", item.copy(), phase.get("evidence_refs"),
                                       "人工理解后的语义标注；持续时间为标注值，不自动将多会话或重叠区间相加。")
            semantic.append(item)
            for member in members:
                points_by_key[member].update(semantic_title=item["title"], semantic_ref=item["ref"])
    observed = [row["input_tokens"] for row in own_rounds if numeric(row.get("input_tokens"))]
    observed_total = sum(observed) if observed else None
    ledger_input = tokens.get("input_tokens")
    reconciliation = {
        "normalized_rounds": len(own_rounds), "observed_input_rounds": len(observed),
        "missing_input_rounds": len(own_rounds) - len(observed), "observed_input": observed_total,
        "trial_ledger_input": ledger_input, "semantic_assigned_rounds": len(assigned),
        "unassigned_or_auxiliary_rounds": len(own_rounds) - len(assigned),
        "ledger_minus_observed": ledger_input - observed_total if numeric(ledger_input) and observed_total is not None else None,
        "time_annotated_rounds": len(elapsed), "unexplained_time_sec": None,
        "note": "差额只有确认同一请求总体与 token 口径后才能解释；未解释时间保持未知，生命周期 phase 可能重叠。",
    }
    reconciliation["usage_subtotals"] = summarize_usage(own_rounds, semantics)
    reconciliation_ref = evidence.add("阶段与账本对账", reconciliation, source)

    def m(label: str, value: Any, unit: str = "", note: str = "", provenance: Any = None) -> dict[str, Any]:
        return metric(label, value, provenance or source, evidence, unit, note)

    metrics = [
        m("报告输入", tokens.get("input_tokens"), "token", "有效/缺失按 Trial 计；覆盖状态另列。缓存关系见口径。", audit.nested(prov, "tokens", "input_tokens")),
        m("报告输出", tokens.get("output_tokens"), "token", provenance=audit.nested(prov, "tokens", "output_tokens")),
        m("模型请求", len(own_rounds) if own_rounds else tokens.get("request_count"), "次", "归一化完成请求；无事件账本时使用 Trial request_count。"),
        m("工具调用", len(own_calls) if own_rounds else process.get("tool_calls"), "次", "工具尝试数不代表同等原子工作量。"),
        m("生命周期耗时", latency.get("duration_sec"), "秒", "超时/取消：" + str(latency.get("censored")), prov.get("duration_sec")),
        m("报告费用", tokens.get("cost_usd"), "USD", "只展示原账本费用；无定价来源时不估算。", audit.nested(prov, "tokens", "cost_usd")),
    ]
    finding_fields = "finding_id candidate_ref candidate_refs focus finding_type adjudication status summary observation direct_evidence evidence_paths interpretation alternative_explanations confidence limitations analyst timestamp first_error_decision key_implementation verifier_consequence conclusion_level root_cause_category"
    own_findings = [row for row in payload.get("findings", []) if row.get("trial_key") == key]
    findings = []
    if depth != "metrics":
        for row in own_findings:
            item = select_fields(row, finding_fields)
            item["ref"] = evidence.add("Finding / " + str(row.get("finding_id") or row.get("focus") or "未命名"), item.copy(), source,
                                       "来自人工 findings；展示层不补做裁决或提升置信度。缺失字段仍未知。")
            level = row.get("conclusion_level")
            item["level"] = {"sample_mechanism": "样本机制", "hypothesis": "假设"}.get(level) or (
                "已裁决发现" if row.get("adjudication") in {"confirmed", "rejected", "indeterminate"} else "未裁决记录")
            findings.append(item)
    candidates = []
    for row in payload.get("candidates", []):
        if row.get("trial_key") == key:
            item = select_fields(row, "focus candidate_type status step_id summary evidence_paths details")
            item["ref"] = evidence.add("候选 / " + str(row.get("candidate_type")), item.copy(), row.get("evidence_paths"), "启发式候选，不能证明违规、责任或根因。")
            candidates.append(item)
    coverage_ref = evidence.add("健康与逐维覆盖", {"health": record.get("health"), "coverage": record.get("coverage")}, source,
                                "健康、verifier 结果、失败模式、完整性裁决与根因分别解释。")
    score_ref = evidence.add("Raw / reconciled verifier", score, prov.get("reward") or source,
                            "总 reward 不替代测试覆盖；本地 validation 和 final claim 不等于独立 verifier。")
    delivery_ref = evidence.add("交付链", {"process": process, "delivery": record.get("delivery")}, source,
                               "mutation/validation 是确定性识别；未记录持久化和 revision 对齐时不能补成完整链。")
    timing_ref = evidence.add("生命周期阶段耗时", latency, prov.get("duration_sec") or source,
                             "阶段可能重叠或缺失；不相加推导等待、模型时间或未解释时间。")
    auto_ref = evidence.add("自动阶段 E/B/I/V/P", boundaries, [row.get("source") for row in own_rounds], "heuristic 投影；不等于人工语义阶段或 runtime phase。")
    contract = select_fields(annotation, "task_contract verifier_explanation") if depth != "metrics" else {}
    contract_ref = evidence.add("任务契约与 verifier 解释", contract, annotation.get("evidence_refs"), "展示输入标注；没有标注时保留缺失。")
    return {
        **select_fields(record, "trial_key job trial task_name model agent adapter health coverage limitations"),
        "depth": depth, "methodology_version": manifest.get("methodology_version"),
        "versions": select_fields(manifest, "schema_version rule_version script_version created_at focus"),
        "outcome": outcome(record), "score": score, "score_ref": score_ref, "coverage_ref": coverage_ref,
        "metrics": metrics, "tokens": tokens, "semantics": semantics,
        "latency": latency, "timing_ref": timing_ref, "delivery": record.get("delivery"),
        "process": process, "delivery_ref": delivery_ref, "findings": findings, "candidates": candidates,
        "contract": contract, "contract_ref": contract_ref, "semantic_stages": semantic,
        "automatic_stages": boundaries, "auto_ref": auto_ref, "curves": curves,
        "reconciliation": reconciliation, "reconciliation_ref": reconciliation_ref,
        "suppressed_findings": len(own_findings) if depth == "metrics" else 0,
    }


def prepare_pair(left: dict[str, Any], right: dict[str, Any], views: list[dict[str, Any]], evidence: Evidence) -> dict[str, Any]:
    grade, reasons = audit.comparison_grade(left, right)
    eligible = grade in {"strict", "conditional"}
    rows = []
    lv, rv = views
    for label, path, unit in (("输入 token", ("tokens", "input_tokens"), "token"),
                              ("完成耗时", ("latency", "duration_sec"), "秒")):
        a, b = audit.nested(left, *path), audit.nested(right, *path)
        exclusions = [] if eligible else ["配对资格不满足"]
        if not numeric(a) or not numeric(b):
            exclusions.append("一侧或双方指标缺失")
        if path[0] == "tokens":
            if lv["tokens"].get("status") != "complete" or rv["tokens"].get("status") != "complete":
                exclusions.append("请求覆盖不完整或未证实")
            declared = lv["semantics"] == rv["semantics"] and lv["semantics"] != "unknown"
            left_source = audit.nested(lv, "tokens", "coverage", "authoritative_source")
            same_ledger = left.get("adapter") and left.get("adapter") == right.get("adapter") and left_source not in {None, "missing"} and left_source == audit.nested(rv, "tokens", "coverage", "authoritative_source")
            if not declared or not same_ledger:
                exclusions.append("缓存包含关系或账本来源未对齐")
        elif lv["latency"].get("censored") is not False or rv["latency"].get("censored") is not False:
            exclusions.append("超时/取消或完成状态未知")
        delta = b - a if not exclusions else None
        fact = {"label": label, "left": a, "right": b, "delta": delta, "unit": unit,
                "n_available": int(not exclusions), "n_excluded": int(bool(exclusions)), "denominator": 1, "exclusions": exclusions}
        fact["ref"] = evidence.add("配对差异 / " + label, fact.copy(), [left["trial_key"], right["trial_key"]], "单 pair 描述；不估计总体效果或因果优越性。")
        rows.append(fact)
    outcomes = [outcome(left), outcome(right)]
    quadrant = "未知或不合格" if not eligible or "未知" in outcomes else " / ".join(outcomes)
    ref = evidence.add("配对资格", {"grade": grade, "reasons": reasons, "outcomes": outcomes, "quadrant": quadrant},
                       [select_fields(item, "trial_key task_name task_checksum baseline prompt_fingerprint verifier_fingerprint") for item in (left, right)],
                       "配置、硬件、并发和遥测差异仍限制因果解释；只有 strict/conditional 可进入配对指标。")
    return {"grade": grade, "reasons": reasons, "ref": ref, "metrics": rows, "quadrant": quadrant}


def build_view(payloads: list[dict[str, Any]], annotations: dict[str, Any] | None = None,
               rounds: list[dict[str, Any]] | None = None, calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    annotations = annotations or {"schema_version": ANNOTATION_VERSION, "trials": {}}
    if annotations.get("schema_version") != ANNOTATION_VERSION or not isinstance(annotations.get("trials"), dict):
        raise ValueError(f"expected {ANNOTATION_VERSION} annotations with trials object")
    records = [(payload, record) for payload in payloads for record in payload["trials"]]
    if not 1 <= len(records) <= 2 or (len(records) == 2 and len(payloads) == 1 and payloads[0]["manifest"].get("mode") != "paired"):
        raise ValueError("HTML v1 supports a single Trial or one Trial pair; Job overview is not supported")
    keys = [record.get("trial_key") for _, record in records]
    if any(not isinstance(key, str) or not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("HTML requires unique nonempty trial_key values; do not merge ambiguous identities")
    if set(annotations["trials"]) - set(keys):
        raise ValueError("annotation trial_key is outside the displayed scope")
    evidence = Evidence()
    views = [prepare_trial(payload, record, annotations["trials"].get(record["trial_key"], {}), rounds or [], calls or [], evidence)
             for payload, record in records]
    pair = prepare_pair(records[0][1], records[1][1], views, evidence) if len(records) == 2 else None
    unmatched = sum(1 for payload in payloads for row in payload.get("findings", []) if row.get("trial_key") not in keys)
    alignment = prepare_semantic_alignment(views, annotations, evidence)
    contributions = prepare_alignment_contributions(views, alignment, pair, evidence)
    return clean({"presentation_version": PRESENTATION_VERSION, "stage_mode": "manual_semantic", "semantic_alignment": alignment,
                  "alignment_contributions": contributions,
                  "trials": views, "pair": pair, "evidence": evidence.rows,
                  "unmatched_findings": unmatched, "scope": "单 Trial" if len(records) == 1 else "配对 Trial"})


def prepare_semantic_alignment(views: list[dict[str, Any]], annotations: dict[str, Any], evidence: Evidence) -> list[dict[str, Any]]:
    """Group reviewed stages by goal without changing either chronological sequence."""
    if any(view["depth"] == "metrics" for view in views):
        return []
    explicit = annotations.get("semantic_alignment")
    if explicit is None:
        groups: dict[str, dict[str, Any]] = {}
        title_counts = [Counter(p.get("title") for p in view["semantic_stages"]) for view in views]
        for view in views:
            for stage in view["semantic_stages"]:
                title = stage.get("title")
                identity = ("key:" + stage["alignment_key"] if stage.get("alignment_key") else
                            "title:" + str(title) if title and all(c[title] <= 1 for c in title_counts) else
                            view["trial_key"] + ":" + stage["stage_id"])
                group = groups.setdefault(identity, {"title": title, "stages": {}})
                group["stages"].setdefault(view["trial_key"], []).append(stage["stage_id"])
        explicit = list(groups.values())
    if not isinstance(explicit, list):
        raise ValueError("semantic_alignment must be an array")
    by_key = {v["trial_key"]: {p["stage_id"]: p for p in v["semantic_stages"]} for v in views}
    assigned: set[tuple[str, str]] = set()
    result = []
    for group in explicit:
        if not isinstance(group, dict) or not group.get("title") or not isinstance(group.get("stages"), dict) or not group["stages"]:
            raise ValueError("semantic alignment requires a title and nonempty stages mapping")
        if set(group["stages"]) - set(by_key):
            raise ValueError("semantic alignment trial is outside displayed scope")
        sides = []
        for view in views:
            key = view["trial_key"]
            ids = group["stages"].get(key, [])
            if not isinstance(ids, list) or any(not isinstance(s, str) or s not in by_key[key] for s in ids):
                raise ValueError("semantic alignment refers to unknown stage_id")
            if len(ids) != len(set(ids)) or any((key, s) in assigned for s in ids):
                raise ValueError("semantic alignment repeats a stage")
            assigned.update((key, s) for s in ids)
            phases = [p for p in view["semantic_stages"] if p["stage_id"] in ids]
            if not phases:
                sides.append(None)
                continue
            side = {"rounds": sum(p["rounds"] for p in phases),
                    "duration_sec": phases[0].get("duration_sec") if len(phases) == 1 else None,
                    "ranges": [select_fields(p, "session_id start_round end_round title ref") for p in phases]}
            for name in ("input", "output", "reasoning", "cache", "uncached"):
                values = [p[name + "_observed"] for p in phases if numeric(p.get(name + "_observed"))]
                side[name + "_observed"] = sum(values) if values else None
                side[name + "_missing"] = sum(p[name + "_missing"] for p in phases)
            sides.append(side)
        absence = group.get("absence_confirmed", [])
        if not isinstance(absence, list) or any(key not in by_key or group["stages"].get(key) for key in absence):
            raise ValueError("absence_confirmed must name displayed trials with no mapped stage")
        if absence and not group.get("evidence_refs"):
            raise ValueError("confirmed structural absence requires evidence_refs")
        item = {"title": group["title"], "summary": group.get("summary"), "sides": sides,
                "absence_confirmed": [v["trial_key"] in absence for v in views]}
        item["ref"] = evidence.add("同目标对齐 / " + str(group["title"]), item.copy(), group.get("evidence_refs"),
                                   "按目标归并；原始时序与全部请求范围保留，一侧缺少对应阶段保持 null。")
        result.append(item)
    # Partial manual maps are allowed, but omitted stages remain visible as unmatched goals.
    if annotations.get("semantic_alignment") is not None:
        for index, view in enumerate(views):
            for phase in view["semantic_stages"]:
                if (view["trial_key"], phase["stage_id"]) not in assigned:
                    side = {**{k: v for k, v in phase.items() if k.endswith("_observed") or k.endswith("_missing")},
                            "rounds": phase["rounds"], "duration_sec": phase.get("duration_sec"),
                            "ranges": [select_fields(phase, "session_id start_round end_round title ref")]}
                    result.append({"title": phase.get("title") or phase["stage_id"], "summary": "未纳入人工对齐的阶段，保留独立展示。",
                                   "sides": [side if i == index else None for i in range(len(views))], "ref": phase["ref"]})
    return result


def prepare_alignment_contributions(views: list[dict[str, Any]], groups: list[dict[str, Any]],
                                    pair: dict[str, Any] | None, evidence: Evidence) -> dict[str, Any]:
    """Signed accounting shares; do not infer missing-side zeros or causal effects."""
    if len(views) != 2 or not groups or any(v["depth"] == "metrics" for v in views):
        return {}
    result = {}
    metrics = {"input_observed": "input_tokens", "output_observed": "output_tokens",
               "reasoning_observed": "reasoning_tokens", "uncached_observed": None, "rounds": "request_count"}
    for metric_name, ledger_field in metrics.items():
        exclusions = []
        if not pair or pair["grade"] not in {"strict", "conditional"}:
            exclusions.append("配对资格不满足")
        if metric_name != "rounds":
            left, right = views
            if any(v["tokens"].get("status") != "complete" for v in views):
                exclusions.append("总账覆盖不完整")
            if left["semantics"] == "unknown" or left["semantics"] != right["semantics"] or not left.get("adapter") or left["adapter"] != right.get("adapter") or not audit.nested(left, "tokens", "coverage", "authoritative_source") or audit.nested(left, "tokens", "coverage", "authoritative_source") != audit.nested(right, "tokens", "coverage", "authoritative_source"):
                exclusions.append("跨侧缓存语义或账本来源未对齐")
        elif not views[0].get("adapter") or views[0]["adapter"] != views[1].get("adapter"):
            exclusions.append("跨 adapter 请求计量口径未对齐")
        if metric_name == "rounds":
            observed = [v["reconciliation"]["normalized_rounds"] for v in views]
        else:
            prefix = metric_name.removesuffix("_observed")
            observed = [v["reconciliation"]["usage_subtotals"][metric_name] for v in views]
            if any(v["reconciliation"]["usage_subtotals"][prefix + "_missing"] for v in views):
                exclusions.append("逐请求指标存在缺失")
        if any(not numeric(x) for x in observed):
            exclusions.append("逐请求指标不可用")
        totals = [v["tokens"].get(ledger_field) if ledger_field else None for v in views]
        if metric_name == "uncached_observed":
            totals = []
            for v in views:
                value, cached = v["tokens"].get("input_tokens"), v["tokens"].get("cache_read_tokens")
                totals.append(value - cached if v["semantics"] == "includes_cache" and numeric(value) and numeric(cached) and 0 <= cached <= value else
                              value if v["semantics"] == "excludes_cache" and numeric(value) else None)
        canonical = all(numeric(x) for x in totals)
        if not canonical:
            totals = observed
        elif metric_name == "rounds" and any(total < value for total, value in zip(totals, observed)):
            exclusions.append("总账请求数小于已观察请求，范围未对账")
        denominator = totals[1] - totals[0] if all(numeric(x) for x in totals) and not exclusions else None
        items = []
        for group in groups:
            values, why, structural = [], [], False
            for index, side in enumerate(group["sides"]):
                if side is None:
                    complete_partition = views[index]["reconciliation"]["semantic_assigned_rounds"] == views[index]["reconciliation"]["normalized_rounds"]
                    if group.get("absence_confirmed", [False] * len(views))[index] and complete_partition:
                        values.append(0)  # Accounting identity for reviewed absence, not a missing metric.
                        structural = True
                    else:
                        values.append(None)
                        why.append("一侧无对应标注，未证实为独有工作")
                else:
                    values.append(side.get(metric_name))
                    if metric_name != "rounds" and side.get(metric_name.removesuffix("_observed") + "_missing"):
                        why.append("阶段指标存在缺失")
            delta = values[1] - values[0] if all(numeric(x) for x in values) and not why and not exclusions else None
            items.append({"delta": delta, "share": delta / denominator if numeric(delta) and numeric(denominator) and denominator != 0 else None,
                          "structural_absence": structural, "exclusions": why + exclusions})
        complete = all(numeric(x["delta"]) for x in items)
        residual = denominator - sum(x["delta"] for x in items) if numeric(denominator) and complete else None
        fact = {"denominator": denominator, "scope": "公共总账差异" if canonical else "已观察主请求小计差异",
                "items": items, "residual_delta": residual,
                "residual_share": residual / denominator if numeric(residual) and numeric(denominator) and denominator != 0 else None,
                "complete_partition": complete, "exclusions": exclusions,
                "note": "右减左 / 同范围总差异；负值抵消，允许超过100%，总差异为0时占比无定义。账目分解不是因果贡献；差额另列为辅助/未归属。"}
        fact["ref"] = evidence.add("同目标差额占比 / " + metric_name, fact.copy(), [v["trial_key"] for v in views], fact["note"])
        result[metric_name] = fact
    return result


def detail_filename(key: str, prefix: str = "trial") -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:24]}.html"


def audit_groups(payloads: list[dict[str, Any]]) -> list[list[tuple[dict[str, Any], dict[str, Any]]]]:
    if len(payloads) == 2:
        if any(payload["manifest"].get("mode") == "paired" for payload in payloads):
            raise ValueError("provide two single-Job audits or one paired audit")
        return [[(payload, row) for row in payload["trials"]] for payload in payloads]
    payload = payloads[0]
    if payload["manifest"].get("mode") != "paired":
        return [[(payload, row) for row in payload["trials"]]]
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row in payload["trials"]:
        identity = row.get("job_root") or row.get("job")
        if not identity:
            raise ValueError("paired Job audit requires job_root or job identities")
        grouped[str(identity)].append((payload, row))
    order = [str(item.get("path")) for item in payload["manifest"].get("inputs", [])]
    ordered = [key for key in order if key in grouped]
    ordered.extend(key for key in grouped if key not in ordered)
    if len(ordered) != 2:
        raise ValueError("paired Job audit requires exactly two distinct Job identities")
    return [grouped[key] for key in ordered]


def is_job_scope(payloads: list[dict[str, Any]]) -> bool:
    return sum(len(payload["trials"]) for payload in payloads) > 2 or any(payload["manifest"].get("mode") == "job" for payload in payloads)


def scoped_payload(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    key = record["trial_key"]
    return {**payload, "trials": [record],
            "findings": [row for row in payload.get("findings", []) if row.get("trial_key") == key],
            "candidates": [row for row in payload.get("candidates", []) if row.get("trial_key") == key]}


def scoped_annotations(annotations: dict[str, Any] | None, keys: list[str]) -> dict[str, Any]:
    if annotations is None:
        return {"schema_version": ANNOTATION_VERSION, "trials": {}}
    scoped = {**annotations, "trials": {key: value for key, value in annotations["trials"].items() if key in keys}}
    if "semantic_alignment" in annotations:
        scoped["semantic_alignment"] = [{**group, "stages": {key: ids for key, ids in group["stages"].items() if key in keys},
                                         "absence_confirmed": [key for key in group.get("absence_confirmed", []) if key in keys]}
                                          for group in annotations["semantic_alignment"] if any(key in keys for key in group["stages"])]
    return scoped


def build_job_view(payloads: list[dict[str, Any]], annotations: dict[str, Any] | None = None,
                   rounds: list[dict[str, Any]] | None = None, calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    annotations = annotations or {"schema_version": ANNOTATION_VERSION, "trials": {}}
    if annotations.get("schema_version") != ANNOTATION_VERSION or not isinstance(annotations.get("trials"), dict):
        raise ValueError(f"expected {ANNOTATION_VERSION} annotations with trials object")
    groups = audit_groups(payloads)
    keys = [record.get("trial_key") for group in groups for _, record in group]
    if any(not isinstance(key, str) or not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("HTML requires unique nonempty trial_key values")
    if set(annotations["trials"]) - set(keys):
        raise ValueError("annotation trial_key is outside the displayed scope")
    round_counts = Counter(row.get("trial_key") for row in rounds or [])
    trials, jobs = [], []
    source_by_key = {}
    for index, group in enumerate(groups):
        job_id = f"job-{index + 1}"
        jobs.append({"id": job_id, "label": group[0][1].get("job") or f"Job {index + 1}",
                     "depth": group[0][0]["manifest"].get("depth"),
                     "methodology_version": group[0][0]["manifest"].get("methodology_version")})
        for payload, record in group:
            key = record["trial_key"]
            source_by_key[key] = record
            tokens, latency = record.get("tokens") or {}, record.get("latency") or {}
            declared = annotations["trials"].get(key, {}).get("input_token_semantics", "unknown")
            if declared not in {"includes_cache", "excludes_cache", "unknown"}:
                raise ValueError(f"invalid input_token_semantics for {key}")
            depth = payload["manifest"].get("depth")
            findings = [] if depth == "metrics" else [
                {**select_fields(row, "finding_id finding_type focus summary observation interpretation adjudication confidence conclusion_level root_cause_category"),
                 "has_direct_evidence": bool(row.get("direct_evidence"))}
                for row in payload.get("findings", []) if row.get("trial_key") == key]
            candidates = [select_fields(row, "candidate_type focus summary status")
                          for row in payload.get("candidates", []) if row.get("trial_key") == key]
            selected = any(key in {item.get("left_trial_key"), item.get("right_trial_key")}
                           for item in payload.get("selection", []))
            metrics = {
                "rounds": round_counts.get(key) if key in round_counts else tokens.get("request_count"),
                "duration_sec": latency.get("duration_sec"), "input_tokens": tokens.get("input_tokens"),
                "cost_usd": tokens.get("cost_usd"),
            }
            trials.append({
                **select_fields(record, "trial_key task_name trial model agent adapter health coverage"),
                "job_id": job_id, "depth": depth, "outcome": outcome(record), "metrics": metrics,
                "round_source": "normalized" if key in round_counts else "request_ledger",
                "censored": latency.get("censored"), "token_status": tokens.get("status"),
                "token_source": audit.nested(tokens, "coverage", "authoritative_source"), "semantics": declared,
                "score": record.get("score"), "selected": selected, "findings": findings, "candidates": candidates,
                "detail": detail_filename(key),
            })
    by_key = {row["trial_key"]: row for row in trials}
    pairs = []
    if len(groups) == 2:
        comparability = audit.build_comparability([[record for _, record in group] for group in groups])
        for item in comparability:
            left_key, right_key = item.get("left_trial_key"), item.get("right_trial_key")
            pair = select_fields(item, "task_name left_trial_key right_trial_key grade reasons")
            pair["detail"] = detail_filename(f"{left_key}\n{right_key}", "pair") if left_key and right_key else None
            if left_key and right_key:
                left, right = source_by_key[left_key], source_by_key[right_key]
                evidence = Evidence()
                views = [{"tokens": record.get("tokens") or {}, "semantics": by_key[record["trial_key"]]["semantics"],
                          "latency": record.get("latency") or {}} for record in (left, right)]
                prepared = prepare_pair(left, right, views, evidence)
                pair["metrics"] = [{key: value for key, value in metric.items() if key != "ref"}
                                   for metric in prepared["metrics"]]
                a, b = by_key[left_key], by_key[right_key]
                round_values = [a["metrics"]["rounds"], b["metrics"]["rounds"]]
                round_exclusions = []
                if pair["grade"] not in {"strict", "conditional"}:
                    round_exclusions.append("配对资格不满足")
                if not all(numeric(value) for value in round_values):
                    round_exclusions.append("轮次缺失")
                if a["round_source"] != b["round_source"] or a.get("adapter") != b.get("adapter"):
                    round_exclusions.append("轮次来源或 adapter 不一致")
                pair["metrics"].insert(0, {"label": "模型轮次", "unit": "轮", "left": round_values[0], "right": round_values[1],
                                            "delta": round_values[1] - round_values[0] if not round_exclusions else None,
                                            "n_available": int(not round_exclusions), "n_excluded": int(bool(round_exclusions)),
                                            "denominator": 1, "exclusions": round_exclusions})
                pair["outcome"] = prepared["quadrant"]
            else:
                pair["metrics"], pair["outcome"] = [], "缺少对应 Trial"
            pairs.append(pair)
    return clean({
        "kind": "job", "presentation_version": "job-html/1", "scope": "双 Job 配对" if len(jobs) == 2 else "Job 总览",
        "jobs": jobs, "trials": trials, "pairs": pairs, "details_dir": "",
        "focus": sorted({focus for payload in payloads for focus in payload["manifest"].get("focus", [])}),
        "bootstrap": {"seed": audit.BOOTSTRAP_SEED, "samples": audit.BOOTSTRAP_SAMPLES},
        "unmatched_findings": sum(1 for payload in payloads for row in payload.get("findings", []) if row.get("trial_key") not in keys),
    })


def render_document(view: dict[str, Any]) -> str:
    css = (ASSETS / "report.css").read_text(encoding="utf-8")
    js = (ASSETS / ("job.js" if view.get("kind") == "job" else "report.js")).read_text(encoding="utf-8")
    if view.get("kind") == "job":
        js = (ASSETS / "job-statistics.js").read_text(encoding="utf-8") + "\n" + js
    serialized = json.dumps(view, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026").replace(">", "\\u003e")
    digest = hashlib.sha256(js.encode()).digest()
    script_hash = base64.b64encode(digest).decode()
    title = html.escape(view["scope"] + " · 轨迹审计")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; worker-src blob:; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>{title}</title><style>{css}</style></head><body><main id="app"></main>
<noscript>此自包含报告需要 JavaScript 展示图表。事实与人工裁决仍可在 audit.json / findings.jsonl / report.md 中复核。</noscript>
<script id="audit-data" type="application/json">{serialized}</script><script>{js}</script></body></html>'''


def run(args: argparse.Namespace) -> dict[str, Any]:
    sources = [path.resolve() for path in args.inputs]
    if not 1 <= len(sources) <= 2:
        raise ValueError("provide one audit or two Trial/Job audits")
    payloads = [load_audit(path) for path in sources]
    output = args.output.resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("HTML output must have .html extension")
    protected = [path.resolve() for path in (getattr(args, "annotations", None),) if path]
    normalized = getattr(args, "normalized", None)
    if normalized:
        protected.append(normalized.resolve())
    for payload in payloads:
        for item in payload["manifest"].get("inputs", []):
            if item.get("path"):
                protected.append(Path(item["path"]).resolve())
        for record in payload["trials"]:
            if record.get("trial_root"):
                protected.append(Path(record["trial_root"]).resolve())
    if any(output == path or path in output.parents for path in protected):
        raise ValueError("HTML output must not overwrite annotations, normalized events, or raw input")
    annotations = read_json(args.annotations) if getattr(args, "annotations", None) else None
    rounds, calls = [], []
    if normalized:
        _, rounds, calls = actions.load_normalized(normalized.resolve())
    job_scope = is_job_scope(payloads)
    view = build_job_view(payloads, annotations, rounds, calls) if job_scope else build_view(payloads, annotations, rounds, calls)
    artifacts = []
    if job_scope:
        details = output.with_name(output.stem + "-details")
        for payload in payloads:
            for record in payload["trials"]:
                key = record["trial_key"]
                target = details / detail_filename(key)
                artifacts.append((target, [scoped_payload(payload, record)], [key]))
        lookup = {record["trial_key"]: (payload, record) for payload in payloads for record in payload["trials"]}
        for pair in view["pairs"]:
            if pair["detail"]:
                members = [pair["left_trial_key"], pair["right_trial_key"]]
                artifacts.append((details / pair["detail"], [scoped_payload(*lookup[key]) for key in members], members))
        for path, _, _ in artifacts:
            resolved = path.resolve()
            if any(resolved == source or source in resolved.parents for source in protected):
                raise ValueError("detail pages must not overwrite raw input or annotation sources")
        view["details_dir"] = details.name + "/"
        output.parent.mkdir(parents=True, exist_ok=True)
        rounds_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        calls_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rounds:
            rounds_by_key[str(row.get("trial_key"))].append(row)
        for row in calls:
            calls_by_key[str(row.get("trial_key"))].append(row)
        # Stage on disk to validate every page before replacing generated outputs,
        # without retaining all documents or full trajectories on the homepage.
        with tempfile.TemporaryDirectory(prefix=".audit-html-", dir=output.parent) as temporary:
            staging = Path(temporary)
            for target, scoped, members in artifacts:
                member_rounds = [row for key in members for row in rounds_by_key[key]]
                member_calls = [row for key in members for row in calls_by_key[key]]
                detail_view = build_view(scoped, scoped_annotations(annotations, members), member_rounds, member_calls)
                detail_view["overview_href"] = "../" + output.name
                (staging / target.name).write_text(render_document(detail_view), encoding="utf-8")
            details.mkdir(parents=True, exist_ok=True)
            for target, _, _ in artifacts:
                (staging / target.name).replace(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.atomic_write(output, render_document(view))
    return {"output": str(output), "trials": len(view["trials"]), "presentation_version": view["presentation_version"],
            "detail_pages": len(artifacts),
            "manual_files_preserved": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, metavar="AUDIT")
    parser.add_argument("--output", required=True, type=Path, help="generated report.html path")
    parser.add_argument("--normalized", type=Path, help="optional normalized event directory")
    parser.add_argument("--annotations", type=Path, help=f"optional {ANNOTATION_VERSION} JSON")
    args = parser.parse_args()
    try:
        result = run(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
