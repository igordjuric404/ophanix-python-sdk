---
type: project-context-guide
id: GUIDE-ophanix-python-sdk-project-context
repo: ophanix-python-sdk
status: active
created: 2026-05-25
last_updated: 2026-05-25
last_reviewed: 2026-05-25
last_verified_commit: unknown
owner: unassigned
canonical: true
stability: active
code_paths: []
tags: [agent-docs, navigation, sdk]
---

# Project Context

## Purpose

`project-context/` is the agent-oriented knowledge layer for this SDK repository. It tells agents where runtime code, tests, examples, release checks, docs, and tracked decisions live.

## Read Order

1. `MAP.md` for repository purpose and navigation.
2. `FEATURE_MAP.md` for SDK feature ownership.
3. `CODEBASE_MAP.md` for source, tests, examples, and release tooling.
4. `INDEX.yaml` for machine-readable lookup.
5. Root SDK docs when the task touches public API behavior.

## Required Structure

Use Markdown with YAML frontmatter for authored knowledge. Use `INDEX.yaml` only as a lookup index. Keep long generated evidence under `_generated/` or `assets/`, then summarize it in Markdown.

## Naming Conventions

- Markdown docs: lowercase kebab-case unless using stable IDs.
- Features: `FEAT-0001-feature-slug.md`.
- Decisions: `ADR-0001-decision-slug.md`.
- Time-bound packages: `YYYY-MM-DD-slug/`.
- Generated reports: `_generated/`.

## Agent Rules

- Treat `src/ophanix_tool_gateway/` as the canonical package surface.
- Update public docs when behavior, errors, CLI commands, or configuration changes.
- Add or update tests before changing supported SDK behavior.
- Do not commit secrets, live tokens, or generated build artifacts.
