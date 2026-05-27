# AGENTS.md

## Project Context

This repository uses `project-context/` as the development-agent source of truth for maps, feature ownership, code organization, decisions, audits, issues, plans, logs, QA, and security notes.

Start with:

1. `project-context/MAP.md`
2. `project-context/FEATURE_MAP.md`
3. `project-context/CODEBASE_MAP.md`
4. `project-context/INDEX.yaml`

## Working Rules

- Before changing behavior, check related feature docs, decisions, open issues, and active implementation plans.
- Prefer canonical project-context documents where `canonical: true`.
- Check `last_reviewed` and `last_verified_commit` before trusting a document.
- If documentation conflicts with code, verify the code and update the stale document.
- Keep root instruction files short. Put detailed knowledge in `project-context/`.

## Decision Precedence

1. Current code and tests
2. Accepted decisions in `project-context/decisions/`
3. Active feature and specification docs
4. Active implementation plans
5. Research notes
6. Archived or generated documents

## Validation

Run the smallest relevant test set first, then broaden when the change crosses module or behavior boundaries. Record important validation evidence in execution logs or issue files when the work affects project-context resources.
