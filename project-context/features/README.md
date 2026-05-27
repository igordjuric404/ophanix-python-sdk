---
type: folder-guide
id: GUIDE-ophanix-python-sdk-features
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
tags: [features, guide]
---

# Features

## Purpose

Store durable feature-level context that spans more than one source file, test, plan, or decision.

## Required Structure

Each feature doc must follow `project-context/templates/feature-template.md` and include purpose, owned paths, workflows, invariants, validation, and related artifacts.

## Naming Conventions

- Use `FEAT-0001-feature-slug.md`.
- Keep IDs stable once referenced.
- Use lowercase kebab-case after the ID.

## Examples

- `FEAT-0001-tool-gateway-client.md`
- `FEAT-0002-cli-bootstrap-checks.md`

## Agent Rules

- Start with `../FEATURE_MAP.md`; create a feature doc only when the map is too small for the context.
- Link related issues, plans, ADRs, tests, and source paths.
- Update the feature doc when behavior or ownership changes.
