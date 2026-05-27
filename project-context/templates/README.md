---
type: folder-guide
id: GUIDE-ophanix-python-sdk-templates
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
tags: [templates, guide]
---

# Templates

## Purpose

Provide reusable structures for project-context files so audits, issues, plans, logs, research, decisions, maps, and feature docs stay consistent.

## Required Structure

Each template must include frontmatter placeholders and only the sections agents need to produce useful, maintainable artifacts.

## Naming Conventions

- Use lowercase kebab-case.
- End Markdown templates with `-template.md`.
- End YAML templates with `-template.yaml`.

## Examples

- `feature-template.md`
- `issue-template.md`
- `implementation-plan-template.md`

## Agent Rules

- Start from the nearest matching template before creating structured project-context files.
- Prefer one reusable template over repeating instructions in every folder guide.
- Update templates when prompts or schema rules change.
