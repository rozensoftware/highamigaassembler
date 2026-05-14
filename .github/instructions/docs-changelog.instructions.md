---
description: "Use when updating README, docs, and changelog entries for user-visible compiler behavior changes or workflow updates."
applyTo:
  - "docs/**/*.md"
  - "README.md"
---

# Documentation and Changelog Instructions

## Primary Goal

Keep documentation synchronized with actual compiler behavior and keep changelog entries useful for users and contributors.

## Documentation Rules

- Prefer evidence-based updates tied to actual code or example behavior.
- Update only impacted sections instead of rewriting unrelated content.
- Keep terminology consistent across README and docs.
- Ensure linked files and anchors remain valid after edits.

## Changelog Rules

- Record every user-visible behavior change in docs/CHANGELOG.md.
- Describe what changed, why it matters, and any migration impact.
- Group entries under clear sections such as Added, Changed, Fixed, and Breaking Changes.

## Quality Gate

- If behavior, syntax, or workflow changed, confirm at least one doc location and changelog are updated together.
- If only internal refactoring occurred, avoid noisy changelog entries.

## Review Output Expectations

- List updated files.
- Summarize user-facing impact in plain terms.
- Flag unresolved documentation ambiguity explicitly.
