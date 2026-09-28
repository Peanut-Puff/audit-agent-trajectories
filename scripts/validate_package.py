#!/usr/bin/env python3
"""Validate repository packaging, versions, links, and skill metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "audit-agent-trajectories"
ENTRY = SKILL / "SKILL.md"
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def linked_markdown(source: Path, errors: list[str]) -> set[Path]:
    linked: set[Path] = set()
    for target in LINK_RE.findall(source.read_text(encoding="utf-8")):
        if "://" in target or target.startswith("#"):
            continue
        path = (source.parent / target.split("#", 1)[0]).resolve()
        if not path.exists():
            fail(f"missing link from {source.relative_to(ROOT)}: {target}", errors)
        elif path.suffix == ".md":
            linked.add(path)
    return linked


def main() -> int:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_RE.fullmatch(version):
        fail(f"VERSION is not SemVer: {version!r}", errors)

    required = [
        ENTRY,
        SKILL / "agents" / "openai.yaml",
        SKILL / "references" / "methodology-index.md",
        SKILL / "scripts" / "audit_trajectories.py",
        SKILL / "scripts" / "test_audit_trajectories.py",
    ]
    for path in required:
        if not path.is_file():
            fail(f"missing required file: {path.relative_to(ROOT)}", errors)

    entry_text = ENTRY.read_text(encoding="utf-8")
    if not re.search(r"(?m)^name:\s*audit-agent-trajectories\s*$", entry_text):
        fail("SKILL.md name is missing or incorrect", errors)
    if not re.search(r"(?m)^description:\s*\S", entry_text):
        fail("SKILL.md description is missing", errors)

    script_text = (SKILL / "scripts" / "audit_trajectories.py").read_text(encoding="utf-8")
    method_match = re.search(r'METHODOLOGY_VERSION\s*=\s*"([^"]+)"', script_text)
    method_version = method_match.group(1) if method_match else None
    if method_version != version:
        fail(f"METHODOLOGY_VERSION {method_version!r} does not match VERSION {version!r}", errors)
    index_text = (SKILL / "references" / "methodology-index.md").read_text(encoding="utf-8")
    if f"`{version}`" not in index_text:
        fail("methodology-index.md does not declare VERSION", errors)

    try:
        compile(script_text, str(SKILL / "scripts" / "audit_trajectories.py"), "exec")
        test_text = (SKILL / "scripts" / "test_audit_trajectories.py").read_text(encoding="utf-8")
        compile(test_text, str(SKILL / "scripts" / "test_audit_trajectories.py"), "exec")
    except SyntaxError as error:
        fail(f"Python syntax error: {error}", errors)

    all_docs = {path.resolve() for path in SKILL.rglob("*.md")}
    reachable: set[Path] = set()
    queue = [ENTRY.resolve()]
    while queue:
        source = queue.pop()
        if source in reachable:
            continue
        reachable.add(source)
        queue.extend(linked_markdown(source, errors) - reachable)
    for orphan in sorted(all_docs - reachable):
        fail(f"orphan skill document: {orphan.relative_to(ROOT)}", errors)

    repository_docs = [
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts
    ]
    for source in repository_docs:
        linked_markdown(source.resolve(), errors)

    junk = [
        path for path in SKILL.rglob("*")
        if path.name == ".DS_Store" or path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    for path in junk:
        fail(f"generated/junk file in skill: {path.relative_to(ROOT)}", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Valid package: audit-agent-trajectories v{version} "
        f"({len(all_docs)} skill Markdown files, {len(repository_docs)} repository Markdown files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
