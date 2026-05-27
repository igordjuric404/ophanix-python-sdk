---
type: codebase-map
id: CODEBASE-MAP-ophanix-python-sdk
repo: ophanix-python-sdk
status: active
created: 2026-05-25
last_updated: 2026-05-27
last_reviewed: 2026-05-27
last_verified_commit: unknown
owner: unassigned
canonical: true
stability: active
code_paths:
  - src/ophanix_tool_gateway/**
  - tests/**
  - examples/**
  - scripts/**
tags: [codebase, navigation, sdk]
---

# Codebase Map: Ophanix Python SDK

## Purpose

Implementation-level router for agents. Use this after `MAP.md` and `FEATURE_MAP.md` to choose source, tests, examples, release tooling, and public docs.

## Implementation Areas

| Path | Contains | Agent Use |
|---|---|---|
| `src/ophanix_tool_gateway/__init__.py` | Public package exports. | Update when public classes, functions, version, or import surface changes. |
| `src/ophanix_tool_gateway/sdk.py` | Main SDK implementation. | Start here for clients, config, errors, retries, caching, auth, telemetry, validation, and HTTP behavior. |
| `src/ophanix_tool_gateway/cli.py` | Installed CLI entrypoint. | Start here for command behavior, environment handling, argument parsing, and JSON output. |
| `src/ophanix_tool_gateway/py.typed` | Typing marker. | Keep for typed package distribution. |
| `tests/test_sdk_behavior.py` | SDK behavioral tests. | Update for client contract, validation, error, retry, cache, auth, telemetry, and response handling changes. |
| `tests/test_package_smoke.py` | Package and CLI smoke tests. | Update for import/export, metadata, packaging, or CLI command changes. |
| `examples/` | Example worker/client usage. | Update when recommended usage patterns change. |
| `scripts/validate_release.py` | Release validation. | Run or update when packaging, docs, exports, release checks, or distribution contents change. |
| Root docs | `README.md`, `API_REFERENCE.md`, `MIGRATION.md`, `CHANGELOG.md`, `SECURITY.md` | Update when public behavior, API, migration notes, release notes, or security guidance changes. |

## Routing Matrix

| Task Type | First Files/Dirs | Required Follow-Up |
|---|---|---|
| Sync/async client behavior | `src/ophanix_tool_gateway/sdk.py` | `tests/test_sdk_behavior.py`, public docs |
| Error semantics | `sdk.py` exception classes/raising paths | Tests for sanitized messages and structured fields |
| Retry/idempotency behavior | `sdk.py` retry logic | Behavior tests and API docs |
| Discovery/cache behavior | `sdk.py` discovery/cache paths | Behavior tests and README/API docs |
| CLI command behavior | `src/ophanix_tool_gateway/cli.py` | Smoke tests and README CLI examples |
| Package exports | `__init__.py`, `pyproject.toml` | Smoke tests and release validation |
| Release contents | `pyproject.toml`, `scripts/validate_release.py` | Changelog/migration docs as needed |
| Examples/security docs | `examples/`, `README.md`, `SECURITY.md` | Ensure examples use env vars and no embedded credentials |

## Test Routing

| Change Surface | Focused Validation |
|---|---|
| SDK behavior | `python -m pytest tests/test_sdk_behavior.py` |
| CLI/package smoke | `python -m pytest tests/test_package_smoke.py` |
| Whole package | `python -m pytest` |
| Lint | `python -m ruff check .` |
| Type checking | `python -m mypy` |
| Release validation | `python scripts/validate_release.py` |
| Security dependencies | `python -m pip_audit` when security extras are installed |

## Config And Entry Points

| File | Purpose |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, optional dev/release/security dependencies, pytest config, ruff config, mypy config, and console script. |
| `README.md` | Primary user guide and usage examples. |
| `API_REFERENCE.md` | Detailed public API contract. |
| `AGENTS.md`, `CLAUDE.md` | Root agent routing. |
| `project-context/INDEX.yaml` | Machine-readable project-context lookup. |

## Documentation Authority

| Document Type | Authority |
|---|---|
| Source/tests | Highest authority for implemented behavior. |
| `README.md`, `API_REFERENCE.md` | Public contract docs; must match implemented behavior. |
| `MIGRATION.md`, `CHANGELOG.md` | Compatibility and release history. |
| `SECURITY.md` | Security handling and vulnerability guidance. |
| `project-context/` | Agent routing, decisions, plans, issues, and logs. |

## Conventions

- Keep public errors sanitized and useful through structured fields.
- Prefer explicit config and typed dataclasses over ad hoc dictionaries for SDK contracts.
- Keep examples runnable with environment variables rather than embedded credentials.
- Keep project-context docs as agent routing and decision memory, not a duplicate API reference.
- Do not expose planned control-plane surfaces until their contracts are stable.

## Ignored Surfaces

Ignore `dist/`, `build/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, and `__pycache__/` for normal documentation and code navigation.
