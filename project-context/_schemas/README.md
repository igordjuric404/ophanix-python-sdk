---
type: folder-guide
id: GUIDE-ophanix-python-sdk-schemas
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
tags: [schemas, guide]
---

# Schemas

## Purpose

Define lightweight machine-readable rules for project-context metadata and lookup files.

## Required Structure

- `frontmatter.schema.yaml` describes required Markdown frontmatter fields.
- `index.schema.yaml` describes the shape of `../INDEX.yaml`.

## Naming Conventions

- Use lowercase kebab-case plus `.schema.yaml`.
- Keep schemas descriptive rather than tool-specific unless a validator is added.

## Examples

- `frontmatter.schema.yaml`
- `index.schema.yaml`

## Agent Rules

- Update schemas when adding required fields or new canonical lookup sections.
- Do not make schemas the narrative source of truth; link to docs and templates instead.
