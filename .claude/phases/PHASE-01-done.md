# Phase 01 — Skeleton
Status: DONE

## Goal
Stand up an installable, strictly-typed Python package skeleton with the project's
data models, exception hierarchy, configuration files, decision log, and committed
directory tree — verified by tests, ruff, and pyright --strict.

## Tasks
- [x] pyproject.toml (src layout, runtime deps, dev group, console entrypoint, ruff/pyright/pytest config)
- [x] uv environment created; all 44 deps installed
- [x] zwiadbrain.toml (operational config incl. [lawbrain] with discover=false)
- [x] .env.example (CONGRESS / LEGISCAN / ANTHROPIC keys + LAW_BRAIN_PATH)
- [x] DECISIONS.md seeded (17 plan decisions + 2 project-start decisions)
- [x] src/zwiadbrain package skeleton (__init__ with __version__; subpackage __init__s)
- [x] exceptions.py (AppError base + typed subclasses) — TDD
- [x] models.py (CommentarySource, Action, Amendment, TextVersion, LegHistory + parts, WikiItem, Bill, EnforcementAction, parse_wiki_item) — TDD
- [x] cli.py + __main__.py (typer entrypoint, `version` command) — TDD
- [x] committed wiki/ tree (federal + 7 states × {bills,enforcement}) + wiki/README.md
- [x] .claude/phases/ tracking established

## Acceptance Criteria
- [x] `uv run pytest` green (22 passed)
- [x] `uv run ruff check .` clean
- [x] `uv run pyright` (strict) — 0 errors
- [x] `python -m zwiadbrain version` and `zwiadbrain version` print 0.1.0
- [x] Package imports without side effects

## Decisions Made This Phase
- models.py imports datetime module-qualified (`dt`) to avoid the `date` field/type name collision (a field named `date` of type `date` evaluates its annotation as `None | None`).
- WikiItem base omits the `type` discriminator; each concrete subclass declares its own `Literal` (avoids the mutable-field invariance conflict under pyright strict).
- Mutable list/dict defaults use direct `= []` / `= {}` (pydantic v2 copies per instance) instead of `Field(default_factory=...)`, for clean strict typing; guarded by a default-isolation test.
- Typer app uses a public `root` callback so it stays a multi-command group while only `version` is wired up.
- `config.py` loader deferred to the phase that first needs it — PHASE-01 kept to the listed deliverables (no scope pull-forward).
