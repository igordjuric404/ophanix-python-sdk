---
type: folder-guide
id: GUIDE-ophanix-python-sdk-decisions
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
tags: [decisions, adr, guide]
---

# Decisions

## Purpose

Store stable architectural decision records for choices that affect repository behavior, organization, contracts, or long-lived workflows.

## Required Structure

- `index.md` lists ADR status and links.
- `ADR-0001-decision-slug.md` files hold individual decisions.
- Use `project-context/templates/decision-template.md`.

## Naming Conventions

- Use `ADR-0001-decision-slug.md`.
- Do not move ADRs between status folders.
- Track status in frontmatter: `proposed`, `accepted`, `superseded`, or `archived`.

## Examples

- `ADR-0001-limit-sdk-to-tool-gateway.md`
- `ADR-0002-public-error-redaction-policy.md`

## Agent Rules

- Create an ADR when a choice changes architecture, public contracts, execution order, or repo organization.
- Link the research, issue, audit, or plan that forced the decision.
- Update `index.md` whenever an ADR is added or superseded.
