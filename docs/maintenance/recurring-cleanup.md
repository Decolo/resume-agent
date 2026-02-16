# Recurring Code Cleanup Workflow

This document describes the periodic maintenance tasks to keep the codebase clean and prevent technical debt accumulation.

## Philosophy

From the Harness Engineering article: "Agents replicate existing patterns, including bad ones." Regular cleanup prevents bad patterns from spreading.

## Weekly Cleanup Tasks

### 1. Dead Code Scan (5 minutes)

```bash
# Find unused imports (ruff catches most, but double-check)
uv run ruff check --select F401 .

# Find functions/classes with no references
# (Manual: search for definitions, check if used)
```

### 2. Test Coverage Check (5 minutes)

```bash
# Run coverage and identify untested code
uv run pytest --cov=resume_agent --cov-report=term-missing

# Focus on new files or recently modified code
git diff main --name-only | grep "\.py$" | xargs uv run pytest --cov-report=term-missing --cov=
```

### 3. Dependency Audit (monthly)

```bash
# Check for outdated dependencies
uv pip list --outdated

# Update dependencies (test thoroughly)
uv sync --upgrade
```

## Agent-Assisted Cleanup

Use Claude Code for deeper analysis:

### Prompt Template 1: Pattern Consistency
```
Scan the codebase for inconsistent patterns:
1. Error handling styles (try/except vs Result types)
2. Logging patterns (logger.info vs print)
3. Type hints (missing or inconsistent)
4. Docstring styles

Report violations and suggest fixes.
```

### Prompt Template 2: Architectural Drift
```
Check for architectural boundary violations:
1. Run test_architecture_boundaries.py
2. Look for circular dependencies
3. Check if new code follows layering (tools → agents → providers)

Report any drift from documented architecture.
```

### Prompt Template 3: Dead Code Detection
```
Find potentially dead code:
1. Functions/classes defined but never called
2. Imports that are never used
3. Config options that are never read
4. Tools registered but never invoked

Be conservative - only flag obvious cases.
```

## Continuous Improvement

### Encode Recurring Issues as Lints

When you find the same issue multiple times:
1. Check if ruff has a rule for it (add to `pyproject.toml`)
2. If not, document in CLAUDE.md or AGENTS.md
3. Consider a custom pytest test (like `test_architecture_boundaries.py`)

### Examples
- "Always use `logger.info()` not `print()`" → Add to style guide
- "Never import from `web/` outside web package" → Already enforced by test
- "All tools must have docstrings" → Could add a test

## Tracking Cleanup Work

Use `docs/plans/active/` for cleanup initiatives:
- Create a plan file: `YYYY-MM-DD-cleanup-<topic>.md`
- Track progress as you work
- Move to `docs/plans/completed/` when done

## Automation Opportunities

Consider adding to CI (`.github/workflows/`):
- Dependency vulnerability scanning (Dependabot)
- Code complexity metrics (radon, mccabe)
- Documentation coverage (interrogate)

Only add if they provide value without noise.
