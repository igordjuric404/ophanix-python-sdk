---
type: feature
id: FEAT-0003
repo: ophanix-python-sdk
status: active
created: 2026-05-27
last_updated: 2026-05-27
last_reviewed: 2026-05-27
last_verified_commit: unknown
owner: unassigned
canonical: true
stability: active
code_paths:
  - pyproject.toml
  - scripts/validate_release.py
  - tests/test_package_smoke.py
source_inputs:
  - CHANGELOG.md
  - MIGRATION.md
related_features:
  - FEAT-0001
  - FEAT-0002
tags: [feature, packaging, release]
---

# Feature: Packaging And Release Validation

## Purpose

Owns distribution metadata, typed package expectations, public exports, release checks, and compatibility documentation.

## Owned Paths

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Metadata, dependencies, optional extras, scripts, build config, and tool config. |
| `scripts/validate_release.py` | Release validation workflow. |
| `tests/test_package_smoke.py` | Import/export and package smoke coverage. |
| `CHANGELOG.md`, `MIGRATION.md` | Release history and compatibility guidance. |

## Invariants

- Distribution contents must include source, docs, tests/examples where expected, and typing marker.
- Console script wiring must match actual CLI module.
- Public exports must be tested.
- Release docs must not advertise unavailable surfaces.

## Validation

```bash
python scripts/validate_release.py
```

Run `python -m pytest tests/test_package_smoke.py` for export or script changes.

## Agent Rules

- Treat packaging metadata as public contract-adjacent.
- Update changelog/migration docs when compatibility changes.
