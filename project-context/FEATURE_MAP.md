---
type: feature-map
id: FEATURE-MAP-ophanix-python-sdk
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
related_features:
  - FEAT-0001
  - FEAT-0002
  - FEAT-0003
  - FEAT-0004
tags: [features, sdk]
---

# Feature Map: Ophanix Python SDK

## Purpose

Routes agents from SDK capabilities to source, tests, docs, examples, and validation. Use this after `MAP.md` and before `CODEBASE_MAP.md`.

## Feature Inventory

| ID | Feature | Status | Primary Paths | Public Docs | Validation |
|---|---|---|---|---|---|
| FEAT-0001 | Tool Gateway Client | active | `src/ophanix_tool_gateway/sdk.py`, `tests/test_sdk_behavior.py` | `README.md`, `API_REFERENCE.md` | `python -m pytest tests/test_sdk_behavior.py` |
| FEAT-0002 | CLI Bootstrap Checks | active | `src/ophanix_tool_gateway/cli.py`, `tests/test_package_smoke.py` | `README.md` | `python -m pytest tests/test_package_smoke.py` |
| FEAT-0003 | Packaging and Release Validation | active | `pyproject.toml`, `scripts/validate_release.py`, `tests/test_package_smoke.py` | `CHANGELOG.md`, `MIGRATION.md` | `python scripts/validate_release.py` |
| FEAT-0004 | Examples and Integration Guidance | active | `examples/`, `README.md`, `SECURITY.md` | `README.md`, `SECURITY.md` | relevant SDK tests plus example review |

## Feature Responsibilities

### FEAT-0001 Tool Gateway Client

Owns sync/async clients, configuration, token providers, tool discovery, compatibility checks, tool invocation, retries, idempotency, caching, telemetry hooks, validation, response-size safeguards, and sanitized exceptions.

Agents should start here when requests mention client methods, gateway calls, auth, tokens, retries, caching, errors, telemetry, or response limits.

### FEAT-0002 CLI Bootstrap Checks

Owns the installed `ophanix-tool-gateway` command, command-line argument parsing, JSON output, environment-variable usage, and smoke-test behavior.

Agents should start here when requests mention command output, CLI options, bootstrap checks, CI smoke usage, or CLI examples.

### FEAT-0003 Packaging and Release Validation

Owns package metadata, typed distribution expectations, public exports, release validation, changelog/migration alignment, and distribution contents.

Agents should start here when requests mention packaging, publishing, versioning, build artifacts, release checks, exports, or compatibility notes.

### FEAT-0004 Examples and Integration Guidance

Owns example usage patterns, worker integration guidance, credential handling examples, and security guidance for SDK consumers.

Agents should start here when requests mention examples, integration patterns, credential handling, worker usage, or security docs.

## Routing By Task

| User Request Mentions | Start With | Then Inspect |
|---|---|---|
| `OphanixToolGatewayClient`, async client, discovery, invocation | FEAT-0001 | `sdk.py`, `tests/test_sdk_behavior.py`, `API_REFERENCE.md` |
| `ophanix-tool-gateway`, CLI JSON, command args | FEAT-0002 | `cli.py`, `tests/test_package_smoke.py`, README CLI section |
| package metadata, PyPI, release, wheel, exports | FEAT-0003 | `pyproject.toml`, `scripts/validate_release.py`, smoke tests |
| example worker, token handling, security guidance | FEAT-0004 | `examples/`, `README.md`, `SECURITY.md` |
| public behavior mismatch | Relevant feature | source, tests, README, API reference |

## Cross-Feature Rules

- Public behavior changes require source, tests, and public docs to agree.
- CLI behavior must stay consistent with SDK configuration and error semantics.
- Packaging changes must not expose planned control-plane surfaces before contracts are stable.
- Examples must not embed live tokens or normalize insecure credential handling.

## Required Feature Docs

- `features/FEAT-0001-tool-gateway-client.md`
- `features/FEAT-0002-cli-bootstrap-checks.md`
- `features/FEAT-0003-packaging-release-validation.md`
- `features/FEAT-0004-examples-integration-guidance.md`
