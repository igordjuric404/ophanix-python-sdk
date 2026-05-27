---
type: feature
id: FEAT-0004
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
  - examples/**
  - README.md
  - SECURITY.md
source_inputs:
  - README.md
  - SECURITY.md
related_features:
  - FEAT-0001
tags: [feature, examples, integration]
---

# Feature: Examples And Integration Guidance

## Purpose

Provides safe usage examples and integration guidance for SDK consumers.

## Owned Paths

| Path | Responsibility |
|---|---|
| `examples/` | Runnable or readable integration examples. |
| `README.md` | Main usage guidance. |
| `SECURITY.md` | Security expectations and vulnerability handling. |

## Invariants

- Examples must use environment variables or injected providers for secrets.
- Examples must not embed live tokens.
- Example behavior should match public API docs.
- Security guidance must stay consistent with SDK token/error behavior.

## Validation

Run relevant SDK tests and manually review examples for token handling when examples change.

## Agent Rules

- Update examples when recommended client usage changes.
- Prefer minimal examples that show safe defaults.
