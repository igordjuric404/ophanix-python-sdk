---
type: project-map
id: MAP-ophanix-python-sdk
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
tags: [map, navigation, sdk]
---

# Project Map: Ophanix Python SDK

## Summary

`ophanix-python-sdk` is the canonical external Python package for Ophanix Tool Gateway client integrations. The current package exposes governed tool discovery, compatibility checks, sync and async tool calls, CLI bootstrap checks, retries, telemetry hooks, response-size safeguards, and sanitized errors.

The repository is small, but the public contract matters. Treat code, tests, and root documentation as a coordinated release surface.

## Repository Role

This repository owns:

- Python package source for `ophanix_tool_gateway`.
- Sync and async Tool Gateway clients.
- Token-provider and configuration behavior.
- CLI entrypoint behavior for bootstrap checks.
- Public package exports.
- Public SDK documentation.
- SDK behavior tests and package smoke tests.
- Release validation tooling.
- Agent-oriented repository memory under `project-context/`.

This repository does not own:

- Tool Gateway server implementation.
- Product-platform backend contracts beyond client-facing assumptions.
- Production deployment topology.
- Demo runtime behavior.
- Future control-plane surfaces until their API contracts are stable.

## Current State

- Runtime implementation is compact and centered under `src/ophanix_tool_gateway/`.
- `README.md` and `API_REFERENCE.md` are user-facing API-adjacent contracts.
- `MIGRATION.md`, `CHANGELOG.md`, and `SECURITY.md` define lifecycle and security expectations.
- `tests/` is compact but behavior-critical.
- `project-context/` is the agent-memory layer for maps, decisions, issues, plans, and logs.
- Existing branch state may include SDK behavior, docs, tests, and CLI changes; verify source before relying on older docs.

## Read Order

Use this order when entering the repo:

1. `AGENTS.md`
2. `project-context/MAP.md`
3. `project-context/FEATURE_MAP.md`
4. `project-context/CODEBASE_MAP.md`
5. `README.md`
6. `API_REFERENCE.md`
7. `pyproject.toml`
8. Source and tests for the affected surface

## Authority Model

When information conflicts, use this precedence:

1. Current source code and tests.
2. Public docs for user-visible contracts.
3. Current `project-context/` docs.
4. Changelog and migration notes.
5. Examples.
6. Historical plans/logs if any are added later.

For public behavior, source/tests and public docs must be reconciled before the work is done.

## Directory Map

This is intentionally shallow. Use `rg --files` for exact files.

```text
ophanix-python-sdk/
|-- AGENTS.md
|-- CLAUDE.md
|-- README.md
|-- API_REFERENCE.md
|-- CHANGELOG.md
|-- MIGRATION.md
|-- SECURITY.md
|-- examples/
|-- project-context/
|   |-- MAP.md
|   |-- FEATURE_MAP.md
|   |-- CODEBASE_MAP.md
|   |-- INDEX.yaml
|   |-- audits/
|   |-- decisions/
|   |-- execution-logs/
|   |-- features/
|   |-- implementation-plans/
|   |-- issues/
|   |-- qa/
|   |-- research/
|   |-- runbooks/
|   |-- security/
|   |-- specifications/
|   `-- templates/
|-- scripts/
|-- src/ophanix_tool_gateway/
`-- tests/
```

## Main Systems

| System | Primary Paths | Responsibility | Start Here When |
|---|---|---|---|
| Tool Gateway client | `src/ophanix_tool_gateway/sdk.py`, `tests/test_sdk_behavior.py`, `API_REFERENCE.md` | Client configuration, sync/async calls, discovery, compatibility, retries, auth, telemetry, validation, and errors. | The request mentions client behavior, gateway calls, errors, retries, auth, response limits, caching, or telemetry. |
| CLI bootstrap | `src/ophanix_tool_gateway/cli.py`, `tests/test_package_smoke.py`, `README.md` | `ophanix-tool-gateway` command behavior and JSON output. | The request mentions CLI commands, smoke checks, command output, or bootstrap usage. |
| Packaging and release | `pyproject.toml`, `scripts/validate_release.py`, `CHANGELOG.md`, `MIGRATION.md` | Package metadata, release validation, versioning, and compatibility notes. | The request mentions package metadata, publishing, release checks, exports, or migration. |
| Examples and integration guidance | `examples/`, `README.md`, `SECURITY.md` | Recommended SDK usage patterns, token handling, and safe integration guidance. | The request mentions examples, worker integration, credentials, or security guidance. |
| Agent memory | `project-context/` | Maps, decisions, issues, plans, logs, schemas, and templates. | The request changes repository organization, workflows, decisions, or long-lived context. |

## Source Code Areas

| Area | Path | Responsibility |
|---|---|---|
| Public exports | `src/ophanix_tool_gateway/__init__.py` | Public import surface and package exports. |
| SDK implementation | `src/ophanix_tool_gateway/sdk.py` | Main client logic, config, models, exceptions, retries, cache, auth, telemetry, and HTTP behavior. |
| CLI | `src/ophanix_tool_gateway/cli.py` | Installed command entrypoint and JSON command behavior. |
| Typing marker | `src/ophanix_tool_gateway/py.typed` | Typed package distribution marker. |

## Documentation Areas

| Area | Path | Use |
|---|---|---|
| Agent context | `project-context/` | Current maps, decisions, issues, plans, logs, schemas, and templates. |
| User guide | `README.md` | Install, setup, sync/async usage, CLI usage, reliability, safety, and examples. |
| API reference | `API_REFERENCE.md` | Public API contract and detailed behavior. |
| Migration guide | `MIGRATION.md` | Compatibility and migration notes. |
| Changelog | `CHANGELOG.md` | Release history and behavior changes. |
| Security guide | `SECURITY.md` | Vulnerability handling and security expectations. |

## Project Context Areas

| Path | Purpose |
|---|---|
| `project-context/MAP.md` | Human-readable repository overview and routing. |
| `project-context/FEATURE_MAP.md` | SDK capability ownership, status, paths, and notes. |
| `project-context/CODEBASE_MAP.md` | More detailed source/test routing. |
| `project-context/INDEX.yaml` | Machine-readable lookup for canonical docs. |
| `project-context/decisions/` | Stable ADRs with status in frontmatter. |
| `project-context/issues/` | Tracked SDK issues by status. |
| `project-context/implementation-plans/` | Active/completed/archived implementation plans. |
| `project-context/execution-logs/` | Work logs and validation evidence. |
| `project-context/templates/` | Reusable artifact templates. |

## Common Workflows

### SDK Behavior Change

1. Identify the public method, config option, exception, or transport behavior involved.
2. Inspect `src/ophanix_tool_gateway/sdk.py`.
3. Update or add behavior tests in `tests/test_sdk_behavior.py`.
4. Update `API_REFERENCE.md` and `README.md` if behavior is user-visible.
5. Run focused tests.
6. Run release validation if metadata, exports, docs, or package behavior changed.

### CLI Change

1. Inspect `src/ophanix_tool_gateway/cli.py`.
2. Check `README.md` CLI examples.
3. Update `tests/test_package_smoke.py` or add CLI-focused coverage.
4. Verify JSON output remains stable and useful.
5. Update public docs if commands, options, or output shape changed.

### Packaging Or Release Change

1. Inspect `pyproject.toml`.
2. Check public exports in `__init__.py`.
3. Run or update `scripts/validate_release.py`.
4. Update `CHANGELOG.md` or `MIGRATION.md` when compatibility changes.
5. Ensure package docs do not advertise unavailable surfaces.

### Documentation-Only Change

1. Determine whether the doc is public user guidance or agent memory.
2. Public behavior docs belong in root docs.
3. Agent routing and decisions belong in `project-context/`.
4. If repeated structure changes, update templates as well.

## Tests And Quality Gates

- `tests/test_sdk_behavior.py` validates client contracts, errors, retries, cache, auth, validation, and response handling.
- `tests/test_package_smoke.py` validates package import/export, metadata, packaging assumptions, and CLI smoke behavior.
- `scripts/validate_release.py` should be used when package metadata, exports, release docs, or distribution behavior changes.
- Public behavior changes require tests and public documentation updates.
- Security-sensitive changes must preserve safe error text and token redaction.

## Generated And Ignored Surfaces

| Path | Treatment |
|---|---|
| `dist/` | Generated release artifacts; exclude by default. |
| `build/` | Generated build output; exclude. |
| `.venv/` | Local Python environment; never canonical. |
| `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` | Generated tool/bytecode caches; exclude. |

## Cross-Repository Relationships

| Repo | Relationship |
|---|---|
| `ophanix-platform/` | Owns Tool Gateway server implementation and product-platform contracts. SDK behavior should align with these contracts. |
| `ophanix-agent-demo/` | May consume or model SDK usage, but does not define SDK public API. |
| `ophanix-site/` | Separate public website boundary. |

## Where Not To Start

- Do not start in `dist/` for source behavior.
- Do not start in examples when changing core SDK contracts; examples are consumers, not the implementation.
- Do not expose planned control-plane modules from docs or exports before contracts are stable.
- Do not treat project-context templates as completed artifacts.

## Agent Decision Flow

Use this flow for ambiguous tasks:

1. Is the change user-visible? Update source, tests, and public docs.
2. Is the change package/release-related? Include release validation.
3. Is the change CLI-related? Validate command behavior and README examples.
4. Is the change security-sensitive? Confirm errors and examples do not leak tokens or raw upstream text.
5. Is the change architectural? Create or update an ADR.

## Update Triggers

Update this map when:

- New public SDK surfaces are added.
- CLI behavior changes.
- Packaging or release workflow changes.
- Root docs are reorganized.
- Cross-repository contract ownership changes.

Update `FEATURE_MAP.md` when capability ownership, status, validation, or primary paths change.

Update `CODEBASE_MAP.md` when source/test routing changes at implementation level.

## Navigation Guide

| Need | Go To |
|---|---|
| Understand repo purpose and boundaries | This map. |
| Find SDK capability ownership | `project-context/FEATURE_MAP.md`. |
| Find source and test routing | `project-context/CODEBASE_MAP.md`. |
| Change public API behavior | `src/ophanix_tool_gateway/sdk.py`, tests, `API_REFERENCE.md`, and `README.md`. |
| Change CLI behavior | `src/ophanix_tool_gateway/cli.py`, smoke tests, and README examples. |
| Change packaging/release behavior | `pyproject.toml`, `scripts/validate_release.py`, `CHANGELOG.md`, and `MIGRATION.md`. |
| Track new work | `project-context/issues/`, `implementation-plans/`, and `execution-logs/`. |

## Decision Rules

- Do not expose planned control-plane surfaces until API contracts are stable.
- Public behavior changes require tests and public doc updates.
- Client errors must remain safe to log and avoid leaking raw upstream text or tokens.
- Treat root docs as user-facing contracts and project-context docs as agent routing and decision memory.
