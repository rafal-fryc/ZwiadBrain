# Phase 02 — Wiki layer
Status: PENDING

## Goal
Render standardized bill/enforcement Markdown pages from the models and rebuild the
SQLite FTS5 index/watchlist from committed frontmatter — fully testable offline.

## Tasks
- [ ] wiki/schema.py — frontmatter pydantic models + validation (incl. commentary_sources)
- [ ] wiki/templates.py — jinja2 bill + enforcement page builders (incl. `## Commentary & Analysis`)
- [ ] pipeline/render.py — model → Markdown+frontmatter; idempotent (compare-then-write, stable key order)
- [ ] store.py — SQLite index with FTS5 derived columns; `reindex` from `wiki/**/*.md`; watchlist queries; `lawbrain_pages` cache table
- [ ] cli: `render`, `reindex` commands

## Acceptance Criteria
- [ ] Render a fixture Bill → frontmatter validates, required sections present
- [ ] `reindex` reconstructs the SQLite index purely from `wiki/**` frontmatter
- [ ] Re-rendering identical input is byte-identical (clean `git status`)
- [ ] pytest + ruff + pyright (strict) all green

## Decisions Made This Phase
(append as you go)
