---
type: folder-guide
id: GUIDE-ophanix-python-sdk-generated
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
tags: [generated, guide]
---

# Generated Outputs

## Purpose

Hold generated indexes, extracts, reports, or tool outputs that support agent work but are not the authored source of truth.

## Required Structure

Use dated subfolders for multi-file outputs: `YYYY-MM-DD-output-slug/`.

## Naming Conventions

- Use lowercase kebab-case.
- Include dates for snapshots.
- Prefer `.md`, `.yaml`, `.json`, `.csv`, or original exported formats.

## Examples

- `2026-05-25-release-validation/`
- `2026-05-25-test-report.md`

## Agent Rules

- Do not treat generated output as canonical unless a human-promoted doc links to it.
- Summarize important generated evidence in the relevant audit, plan, issue, or log.
- Keep bulky exports here or under `../assets/exports/`.
