# Repository Instructions

This repository versions one installable Agent Skill at `skills/audit-agent-trajectories/`.

## Always do

- Keep `SKILL.md` concise and route detailed methods through `references/`.
- Keep the extractor dependency-free at runtime; use the Python standard library.
- Preserve raw input as read-only and never commit audit outputs, credentials, real request archives, or large trial artifacts.
- Keep Markdown links valid and every skill reference reachable from `SKILL.md`.
- Treat health, verifier outcome, failure mode, integrity finding, and root cause as separate conclusions.

## Versioning

- `VERSION` is the repository release version.
- Keep `METHODOLOGY_VERSION` aligned with the published methodology version.
- Bump `RULE_VERSION` when deterministic candidate or adapter semantics change.
- Bump `SCHEMA_VERSION` only for breaking machine-output changes.
- Update `CHANGELOG.md` for releases and follow `docs/versioning.md`.

## Verification

Run the smallest relevant checks, and before a release run:

```bash
python3 scripts/validate_package.py
python3 skills/audit-agent-trajectories/scripts/test_audit_trajectories.py -v
python3 skills/audit-agent-trajectories/scripts/test_normalize_trajectory_events.py -v
python3 skills/audit-agent-trajectories/scripts/test_classify_round_actions.py -v
python3 skills/audit-agent-trajectories/scripts/test_classify_round_stages.py -v
npx skills add . --list
```
