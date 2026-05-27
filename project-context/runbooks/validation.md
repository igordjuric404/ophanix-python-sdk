---
type: runbook
id: RUNBOOK-validation-ophanix-python-sdk
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
  - src/ophanix_tool_gateway/**
  - tests/**
  - scripts/**
source_inputs:
  - pyproject.toml
related_features:
  - FEAT-0001
  - FEAT-0002
  - FEAT-0003
  - FEAT-0004
tags: [runbook, validation, sdk, tests]
---

# Validation Runbook: Ophanix Python SDK

## Purpose

Defines validation for SDK behavior, CLI behavior, packaging, examples, public docs, and project-context changes.

## Prerequisites

- Python `>=3.11`.
- Development dependencies installed:

```bash
python -m pip install -e '.[dev]'
```

Install release or security extras only when needed:

```bash
python -m pip install -e '.[release]'
python -m pip install -e '.[security]'
```

## Command Matrix

| Change Surface | Preferred Command | Notes |
|---|---|---|
| SDK behavior | `python -m pytest tests/test_sdk_behavior.py` | Required for FEAT-0001 behavior changes. |
| CLI/package smoke | `python -m pytest tests/test_package_smoke.py` | Required for FEAT-0002 and package entrypoint changes. |
| Whole package | `python -m pytest` | Use after cross-feature changes. |
| Lint | `python -m ruff check .` | Use for source changes when ruff is installed. |
| Type checking | `python -m mypy` | Use for public SDK source changes. |
| Release validation | `python scripts/validate_release.py` | Required for FEAT-0003 packaging/release changes. |
| Security dependency audit | `python -m pip_audit` | Use when security dependencies are installed and dependency/security changes occur. |
| Project-context docs | YAML/frontmatter parse plus path review | Required for structured docs. |

## Feature-Based Validation

| Feature | Minimal Validation |
|---|---|
| FEAT-0001 Tool Gateway Client | `python -m pytest tests/test_sdk_behavior.py`; update public docs. |
| FEAT-0002 CLI Bootstrap Checks | `python -m pytest tests/test_package_smoke.py`; check README CLI examples. |
| FEAT-0003 Packaging and Release Validation | `python scripts/validate_release.py`; check package metadata and release docs. |
| FEAT-0004 Examples and Integration Guidance | Relevant SDK tests plus manual example review for credential handling. |

## Recommended Execution Order

1. Run the narrowest relevant test first.
2. Run lint/typecheck when source contracts or typing are touched.
3. Run release validation when exports, metadata, docs, or distribution contents change.
4. Run the whole test suite after changes that cross SDK, CLI, and packaging surfaces.
5. Record commands and outcomes in an execution log when the work is tracked.

## Rules

- Public behavior changes require tests and public docs.
- Do not claim examples are safe without checking token handling.
- Do not expose planned control-plane surfaces through exports or docs before contracts are stable.
- If validation cannot run, record the missing prerequisite and residual risk.
