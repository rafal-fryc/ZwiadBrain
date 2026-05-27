# Phase 02 — Wiki layer
Status: DONE

## Goal
Render standardized bill/enforcement Markdown pages from the models and rebuild the
SQLite FTS5 index/watchlist from committed frontmatter — fully testable offline.

## Tasks
- [x] `wiki/schema.py` — frontmatter (de)serialization + validation (metadata only; commentary body excluded)
- [x] `wiki/templates.py` — single jinja2 body template + typed section helpers; `## Commentary & Analysis` marker-fenced + headings demoted (decision 6)
- [x] `pipeline/render.py` — model -> Markdown+frontmatter page; jurisdiction/type path routing; idempotent compare-then-write
- [x] `store.py` — SQLite index with FTS5 derived columns; `reindex` from `wiki/**/*.md`; watchlist (`tracking`) queries; `lawbrain_pages` cache table
- [x] cli: `reindex` command (`render` deferred — see decisions)

## Acceptance Criteria
- [x] Render a fixture Bill -> frontmatter validates, required sections present
- [x] `reindex` reconstructs the SQLite index purely from `wiki/**` frontmatter
- [x] Re-rendering identical input is byte-identical (clean `git status`); `write_page` skips unchanged
- [x] pytest (41) + ruff + pyright (strict) all green

## Decisions Made This Phase
- Frontmatter = metadata only; body = rendered content; commentary verbatim text lives in the body, not frontmatter (DECISIONS.md #20).
- Added content fields to models: `WikiItem.summary`; `EnforcementAction.background/allegations/outcome/significance`; `CommentarySource.body` (body-only, excluded from frontmatter).
- `render.py` placed in `pipeline/` (per plan layout), using `wiki/schema` + `wiki/templates`.
- A single generic jinja2 body template renders a pre-filtered, typed list of `{heading, body}` sections (deterministic; honors "single jinja2 template").
- `write_page` uses compare-then-write with LF newlines for idempotent output / clean `git status`.
- Standalone `render` CLI command DEFERRED to PHASE-03: `render` is a library function (covered by `test_render.py`) but has no model source until a source produces items; re-rendering from a page would strip body content, so a page-only `render` CLI is unsafe.
- Python 3.12 note: `Path.read_text` has no `newline=` kwarg (3.13+); rely on `write_text(newline="\n")` + default `read_text` for LF determinism.
