---
type: project-map
id: MAP-repo-name
repo: repo-name
status: active
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
last_reviewed: YYYY-MM-DD
last_verified_commit: unknown
owner: unassigned
canonical: true
stability: active
code_paths: []
tags: [map, navigation]
---

# Project Map: Repo Name

## Summary

Explain what the repository is and how agents should think about it.

## Repository Role

This repository owns:

- Owned surface.

This repository does not own:

- Out-of-boundary surface.

## Current State

- Current implementation or documentation state that affects agent work.

## Read Order

1. `AGENTS.md`
2. `project-context/MAP.md`
3. `project-context/FEATURE_MAP.md`
4. `project-context/CODEBASE_MAP.md`
5. Repo-specific entrypoint docs.

## Authority Model

When information conflicts, use this precedence:

1. Current source code and tests.
2. Accepted decisions and current project-context docs.
3. Stable repository docs.
4. Historical plans and logs.
5. Generated outputs and local state.

## Directory Map

Use a shallow tree. Include major folders only.

```text
repo-name/
|-- AGENTS.md
|-- README.md
|-- project-context/
|   |-- MAP.md
|   |-- FEATURE_MAP.md
|   |-- CODEBASE_MAP.md
|   |-- INDEX.yaml
|   `-- templates/
|-- src-or-main-area/
|-- tests/
`-- docs/
```

## Main Systems

| System | Primary Paths | Responsibility | Start Here When |
|---|---|---|---|
| System name | `path/` | What it owns. | Trigger or task type. |

## Source Code Areas

| Area | Path | Responsibility |
|---|---|---|
| Area name | `path/` | What it owns. |

## Documentation Areas

| Area | Path | Use |
|---|---|---|
| Agent context | `project-context/` | Current maps, decisions, issues, plans, logs, schemas, and templates. |

## Project Context Areas

| Path | Purpose |
|---|---|
| `project-context/MAP.md` | Human-readable repository overview and routing. |
| `project-context/FEATURE_MAP.md` | Feature ownership and subsystem routing. |
| `project-context/CODEBASE_MAP.md` | More detailed implementation/test routing. |
| `project-context/INDEX.yaml` | Machine-readable lookup for canonical docs. |

## Common Workflows

### Workflow Name

1. Identify the owning feature or system.
2. Inspect source and nearest tests.
3. Implement the smallest scoped change.
4. Run focused validation.
5. Update project-context docs when behavior or decisions change.

## Tests And Quality Gates

- Relevant test or validation surface.

## Automation And Tooling

| Area | Path | Use |
|---|---|---|
| Tooling area | `path/` | What it validates or automates. |

## Generated And Ignored Surfaces

| Path | Treatment |
|---|---|
| `generated-path/` | Exclude from canonical source. |

## Cross-Repository Relationships

| Repo | Relationship |
|---|---|
| `related-repo/` | Boundary and contract. |

## Where Not To Start

- Misleading or generated surface.

## Agent Decision Flow

1. If the task is behavior-related, start with feature, source, and tests.
2. If the task is documentation-related, start with project-context and stable docs.
3. If the task is architectural, create or update an ADR.

## Update Triggers

Update this map when:

- A major directory is added, removed, or repurposed.
- Ownership or cross-repository boundaries change.
- Validation workflows become canonical.

## Navigation Guide

1. Start with this map.
2. Use `FEATURE_MAP.md` for feature ownership.
3. Use `CODEBASE_MAP.md` for detailed source/test routing.

## Decision Rules

- Rule agents should follow before changing this repo.
