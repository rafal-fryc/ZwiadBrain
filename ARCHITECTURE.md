# ZwiadBrain Architecture

> Authoritative current-state document. As of v0.6.0 (2026-05-28).
> Supersedes the architecture sections of `docs/PLAN.md`, which predate the
> 2026-05-27 subagent pivot. For the reasoning behind every choice, see
> `DECISIONS.md` (decisions are append-only and authoritative).

## What ZwiadBrain is

A Python 3.12 CLI that builds a **git-backed Markdown wiki** of U.S. federal
legislation in AI, privacy, and cybersecurity. Each tracked bill is a Markdown
page: validated YAML frontmatter (the watchlist/source-of-truth metadata) plus a
rendered body (summary, status timeline, amendments, legislative history). The
committed `wiki/**` tree **is** the product; the SQLite index under
`data/cache/` is a derived cache rebuilt from frontmatter by `reindex` (D1).

## The execution model: deterministic Python bookends + interactive subagents

All LLM work runs as **interactive Claude Code subagents** (`.claude/agents/*.md`),
dispatched from a human-driven session via slash commands. **Python makes zero
LLM calls** — there is no Anthropic SDK dependency and no API key (D26, D30).

Each slash command is a deterministic Python "fetch" half and a deterministic
Python "render" half with the subagent classification/summarization in between.
The two halves exchange gitignored JSON files under `data/runs/<id>/` (D27):

```
slash command (interactive Claude Code session)
  │
  ├─ fetch  (deterministic Python: HTTP → models → JSON)   ─┐
  │                                                          │  data/runs/<id>/*.json
  ├─ subagents (classifier / summarizer / amendment-        │  (gitignored handoff)
  │             explainer / leg-history researcher+verifier) │
  │                                                          │
  └─ render (deterministic Python: JSON → models →          ─┘
             render_page → wiki/**/*.md → reindex)
```

### Slash commands (the only entry points to LLM work)
- **`/zwiad-backfill`** — discover federal bills (two-stage recall, D33), fetch,
  classify (disqualify rubric, D17), summarize + explain amendments for in-scope
  bills, render pages. Backed by CLI `fetch-candidates` + `render-classified`.
- **`/zwiad-scan-states`** — discover state bills via LegiScan `getSearchRaw`
  full-text search, enrich via `getBill`, classify, summarize + explain amendments
  for in-scope bills, render pages under `wiki/states/<st>/bills/`. State analog
  of `/zwiad-backfill`; loops over `[states].enabled`, each capped by `--limit`
  (D49). Backed by CLI `fetch-state-candidates` + `render-classified` (reused).
- **`/zwiad-leg-history <congress/type/number>`** — assemble a source-linked
  legislative history for one enacted bill: deterministic spine + researched,
  grounded, cross-verified hearings/statements + narrative (D34–D37). On-demand,
  not part of routine scan (D38). Backed by CLI `fetch-leg-history` +
  `render-leg-history`.
- **`/zwiad-refresh`** — re-fetch every tracked federal and state bill, dispatch
  classifier/summarizer/amendment-explainer only where a cursor changed (federal:
  `updateDateIncludingText`; state: `change_hash`, D50), preserve persisted
  leg-history (hearings/statements/narrative, D40), flip out-of-scope bills to
  `tracking: false` without deletion (D39). Federal pass backed by CLI
  `fetch-refreshable`; state pass backed by `fetch-state-refreshable`
  (`getMasterListRaw` change_hash diff → `getBill` on changed bills only). Both
  passes feed the shared `render-refreshed` step.

**Requires an open interactive session.** Nothing is headless or cron-driven:
`claude -p` and the Agent SDK would draw separate metered credit, so they are
deliberately not used (D26). A terminal must be open and the command triggered.

## Three invariants every change MUST preserve

1. **D20 — byte-identical render.** `render_page(model)` is a pure deterministic
   function: unchanged input → identical bytes → clean `git status`. Frontmatter
   holds metadata only, EXCEPT `commentary_sources` and
   `leg_history.{hearings,statements,narrative}` (D37/D40). New model validators
   must not change serialized output.
2. **D36 — grounding trust boundary (fail-closed).** A researched leg-history
   statement persists ONLY if it passes BOTH a deterministic gate (URL returns
   200, normalized verbatim quote present on the page, ≥20 chars) AND an
   independent cross-model verifier (researcher = sonnet, verifier = opus).
   Failures are dropped and logged, never silently persisted.
3. **D26 — interactive-only LLM.** All LLM work is interactive Claude Code
   subagents; Python is deterministic, independently unit-testable tooling.

## Retrieval

Lexical-only: SQLite FTS5/BM25 over columns derived from frontmatter, with regex
key-extraction as the primary matcher. No embeddings, no vector DB (D13).
Legislative tracking is a verbatim-span domain (bill numbers, dockets,
public-law numbers) where lexical precision dominates.

## Source layout

```
src/zwiadbrain/
  cli.py            typer CLI: the deterministic fetch/render halves
  config.py         pydantic-settings (TOML + .env)
  exceptions.py     AppError base + typed subclasses
  models.py         Bill, Amendment, LegHistory, Hearing, Statement, …
  store.py          SQLite FTS5 index + reindex-from-frontmatter
  reference/        topics.yaml taxonomy + DISQUALIFY lexicon + loader
  sources/          congress.py, govinfo.py, legiscan.py (HTTP transport + Bill mapping)
  pipeline/         discover, enrich, render, leg_history, refresh
  wiki/             schema (frontmatter models) + templates (jinja2)
.claude/
  agents/           subagent prompts (classifier, summarizer, …)
  commands/         slash commands (zwiad-backfill, -leg-history, -refresh)
```

## Status

Shipped: PHASE-01..07 (skeleton, wiki layer, federal source, LLM subagents,
legislative history, watchlist refresh, state sources via LegiScan). Current: v0.6.1.

**Not yet implemented:** enforcement actions / FTC + state AGs (PHASE-08),
law-brain commentary + discovery (PHASE-09/11), scheduling (PHASE-10).
`src/zwiadbrain/sources/enforcement/` is a PHASE-08 placeholder.
