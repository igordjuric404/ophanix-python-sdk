---
type: feature
id: FEAT-0002
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
  - src/ophanix_tool_gateway/cli.py
  - tests/test_package_smoke.py
source_inputs:
  - README.md
related_features:
  - FEAT-0001
tags: [feature, cli]
---

# Feature: CLI Bootstrap Checks

## Purpose

Provides the installed `ophanix-tool-gateway` command for tool discovery and call smoke checks.

## Owned Paths

| Path | Responsibility |
|---|---|
| `src/ophanix_tool_gateway/cli.py` | CLI argument parsing, environment handling, command execution, and JSON output. |
| `tests/test_package_smoke.py` | Package and CLI smoke coverage. |
| `README.md` | CLI usage examples. |
| `pyproject.toml` | Console script wiring. |

## Invariants

- CLI output should remain machine-readable JSON.
- CLI token handling must follow SDK security rules.
- CLI examples must match implemented command behavior.

## Validation

```bash
python -m pytest tests/test_package_smoke.py
```

## Agent Rules

- Update README examples when commands/options/output change.
- Keep CLI behavior aligned with SDK config and error semantics.
