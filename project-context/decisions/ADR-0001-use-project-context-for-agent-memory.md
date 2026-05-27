---
type: decision
id: ADR-0001
repo: ophanix-python-sdk
status: accepted
created: 2026-05-27
last_updated: 2026-05-27
last_reviewed: 2026-05-27
last_verified_commit: unknown
owner: unassigned
canonical: true
stability: active
code_paths:
  - project-context/**
source_inputs:
  - project-context/MAP.md
  - project-context/FEATURE_MAP.md
  - project-context/CODEBASE_MAP.md
related_features:
  - FEAT-0001
  - FEAT-0002
  - FEAT-0003
  - FEAT-0004
supersedes: []
superseded_by: null
tags: [adr, project-context, agent-memory, sdk]
---

# ADR-0001: Use Project Context For Agent Memory

## Status

Accepted.

## Context

The SDK repo is small, but it has public API docs, examples, tests, release tooling, and agent-oriented guidance. Autonomous agents need to distinguish public user-facing contracts from internal routing and decision memory.

## Decision

Use `project-context/` as the canonical agent-oriented knowledge layer for maps, feature ownership, codebase routing, decisions, issues, implementation plans, execution logs, validation runbooks, schemas, and templates.

Keep public API/user guidance in root docs such as `README.md` and `API_REFERENCE.md`. Do not duplicate the API reference in project-context docs.

## Consequences

- Agents can route SDK work consistently without bloating public docs.
- Public docs remain focused on SDK consumers.
- Project-context docs can track implementation decisions, validation, and internal navigation.
- Public behavior changes still require source, tests, and public docs to agree.

## Alternatives Considered

- Put agent guidance in root README: rejected because README is user-facing.
- Put all guidance in `AGENTS.md`: rejected because root agent files should stay short.
- Use generated indexes only: rejected because SDK decisions and workflows need human-readable context.

## Links

- `project-context/MAP.md`
- `project-context/FEATURE_MAP.md`
- `project-context/CODEBASE_MAP.md`
- `project-context/runbooks/validation.md`
