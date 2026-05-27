---
type: feature
id: FEAT-0001
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
  - src/ophanix_tool_gateway/sdk.py
  - tests/test_sdk_behavior.py
source_inputs:
  - README.md
  - API_REFERENCE.md
related_features: []
related_issues: []
related_plans: []
related_decisions: []
tags: [feature, sdk, tool-gateway]
---

# Feature: Tool Gateway Client

## Purpose

Provides sync and async Python clients for Ophanix Tool Gateway discovery, compatibility checks, governed tool calls, retries, idempotency, telemetry hooks, validation, and safe error reporting.

## Owned Paths

| Path | Responsibility |
|---|---|
| `src/ophanix_tool_gateway/sdk.py` | Main SDK implementation. |
| `tests/test_sdk_behavior.py` | Behavioral coverage. |
| `README.md` | User guide and usage examples. |
| `API_REFERENCE.md` | Public API contract. |

## Invariants

- Public errors must be safe to log.
- Tokens must not be leaked in errors, telemetry, examples, or docs.
- Public behavior must be represented in tests and public docs.
- Client contracts must stay aligned with Tool Gateway server contracts.

## Validation

```bash
python -m pytest tests/test_sdk_behavior.py
```

Run lint/typecheck when source contracts or typing change.

## Agent Rules

- Update `README.md` and `API_REFERENCE.md` for user-visible behavior.
- Add tests before broadening public behavior.
- Do not expose future control-plane APIs from this feature.
