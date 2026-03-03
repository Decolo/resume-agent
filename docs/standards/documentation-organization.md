# Documentation Organization Standard

This standard defines stable rules for documentation structure, naming, and
lifecycle in this repository.

## Goals

1. Keep documentation discoverable by using predictable locations.
2. Reduce churn from ad-hoc naming and frequent path changes.
3. Preserve historical context without polluting active guidance.

## Directory Taxonomy

Use these directories for new documents:

| Directory | Purpose |
| --- | --- |
| `docs/setup/` | Environment and local runtime setup |
| `docs/architecture/` | Active architecture docs and runtime flow |
| `docs/architecture/adrs/` | Architecture Decision Records |
| `docs/api-reference/` | API and code-level quick references |
| `docs/usage/` | User-facing CLI/API usage |
| `docs/ops/` | CI, release, quality, operational policy |
| `docs/maintenance/` | Recurring repository maintenance workflows |
| `docs/learn/` | Learning material and external concept notes |
| `docs/research/` | Exploratory notes and PoCs |
| `docs/todo/` | Planned technical backlog and future work items |
| `docs/sessions/` | Session persistence and conversation state docs |
| `docs/archive/` | Archived or superseded historical content |

## Naming Rules

1. Use lowercase kebab-case for filenames.
2. Prefer suffixes that reveal document type:
   - `*-guide.md` for step-by-step workflows
   - `*-reference.md` for lookup docs
   - `*-scorecard.md` for metric snapshots
   - `*-policy.md` for rules/governance
3. Avoid generic names at the top level of `docs/` except:
   - `README.md`
   - `README.learn.md`
   - `architecture.md`
4. Do not create version numbers in filenames unless required by an external contract.

## Lifecycle States

Every non-trivial document should be one of:

1. `Active`: referenced by `docs/README.md` or `docs/README.learn.md`
2. `Archived`: moved under `docs/archive/` and labeled as historical
3. `Superseded`: archived with a pointer to the replacement doc

## Change Workflow

When adding or moving docs:

1. Place the file in the correct taxonomy directory.
2. Update links in:
   - `docs/README.md`
   - `docs/README.learn.md`
   - any domain-specific index that references it
3. For renames/moves, run:
   - `rg -n "<old-path-or-old-name>" README.md docs`
4. If content is old but still useful, archive instead of deleting.
5. If deleting, confirm no remaining references and document why in PR description.

## Quality Bar

1. One authoritative source per topic.
2. Keep examples executable or clearly marked as illustrative.
3. Prefer stable semantics over implementation line numbers.
4. Include concrete dates in snapshots (for example `2026-02-28`).
