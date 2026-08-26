# ZwiadBrain Architecture

> Authoritative current-state document. As of v0.9.0.
> Supersedes the architecture sections of `docs/PLAN.md`, which predate the
> 2026-05-27 subagent pivot. For the reasoning behind every choice, see
> `DECISIONS.md` (decisions are append-only and authoritative).

## What ZwiadBrain is

A Python 3.12 CLI that builds a **git-backed Markdown wiki** of U.S. federal and
state legislation and enforcement actions in AI, privacy, and cybersecurity.
Each tracked bill or enforcement matter is a Markdown page: validated YAML
frontmatter (the watchlist/source-of-truth metadata) plus a rendered body
(summary, status timeline, amendments, legislative history). The
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
  An **enacted-only** discovery half for the prior-years backfill,
  `fetch-enacted-candidates` (`/law/{congress}/pub` → two-stage recall → enrich),
  stages *only* bills that became public law; it backs the
  `/zwiad-backfill-enacted` campaign (PHASE-23/D84).
- **`/zwiad-scan-states`** — discover state bills via LegiScan `getSearchRaw`
  full-text search, enrich via `getBill`, classify, summarize + explain amendments
  for in-scope bills, render pages under `wiki/states/<st>/bills/`. State analog
  of `/zwiad-backfill`; loops over `[states].enabled`, each capped by `--limit`
  (D49). Backed by CLI `fetch-state-candidates` + `render-classified` (reused).
  An **enacted-only** discovery half for the prior-years backfill,
  `fetch-state-enacted-candidates` (`getSessionList` → `getMasterList(id=session)` →
  keep `status==4` → free title+description recall), stages *only* bills that became
  law; it backs `/zwiad-backfill-enacted-state` (PHASE-24/D84), distinct from the
  routine `fetch-state-candidates`.
- **`/zwiad-backfill-enacted <congress>`** + **`/zwiad-backfill-enacted-state <st> <year>`** —
  the prior-years **enacted-only** backfill campaign (D84/D85): one Congress / one state-session
  per run, enacted-first discovery → classify → summarize → render, **stopping before commit** for
  a per-unit review gate. Progress tracked in `docs/backfill/enacted-campaign.md`; significant laws
  flagged to `docs/backfill/leg-history-queue.md` for a separate per-law `/zwiad-leg-history` pass.
  Backed by CLI `fetch-enacted-candidates` / `fetch-state-enacted-candidates` + `render-classified`.
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
  passes feed the shared `render-refreshed` step. **No enforcement pass** — re-scan
  is the enforcement refresh (D52).
- **`/zwiad-scan-enforcement`** — discover FTC + state-AG enforcement items via RSS
  feeds and config-driven HTML adapters (D54), classify with the enforcement rubric
  (D55), match to existing matters via strong key (court/FTC docket) then LLM
  matcher with deterministic confirm (D53), extract, and render under
  `wiki/federal/enforcement/` + `wiki/states/<st>/enforcement/`. Re-running this
  command IS the enforcement refresh — there is no enforcement leg in
  `/zwiad-refresh` (D52). Backed by CLI `fetch-enforcement-candidates` +
  `render-enforcement`.
- **`/zwiad-sync-lawbrain`** — attach read-only law-brain commentary (+ a
  `## Further Reading` link section, D62) onto already-tracked bill/enforcement pages
  via deterministic key-matching with a `lawbrain-matcher` LLM fallback gated by a
  fresh-key deterministic confirm (D16/D59). Commentary-only — no stub-minting (D14,
  `discover=false`); sole creator/updater of the `lawbrain:region` block, which other
  re-renders preserve verbatim (D63). Backed by CLI `fetch-lawbrain-candidates` +
  `render-lawbrain-commentary`.
- **`/zwiad-run`** — the whole pipeline in one interactive session: refresh →
  federal discover → state discover → enforcement → law-brain → reindex, with
  per-source failure isolation, an auto-commit per source, and a deterministic
  block appended to `scan-log.md` (`run-log`). This is the scheduling entrypoint
  (PHASE-10, D65/D66): ZwiadBrain ships no cron wiring, so an external runner
  capable of opening an interactive session triggers this one command on a
  cadence. `--dry-run` plans without writing.

**Requires an open interactive session.** Nothing is headless or cron-driven:
`claude -p` and the Agent SDK would draw separate metered credit, so they are
deliberately not used (D26). A terminal must be open and the command triggered.

## Three invariants every change MUST preserve

1. **D20 — byte-identical render.** `render_page(model)` is a pure deterministic
   function: unchanged input → identical bytes → clean `git status`. Frontmatter
   holds metadata only, EXCEPT `commentary_sources`,
   `leg_history.{hearings,statements,narrative}` (D37/D40), and
   `EnforcementAction` prose fields (D56). New model validators must not change
   serialized output.
2. **D36 — grounding trust boundary (fail-closed).** A researched leg-history
   statement persists ONLY if it passes BOTH a deterministic gate (URL returns
   200, normalized verbatim quote present on the page, ≥20 chars) AND an
   independent cross-model verifier (researcher = sonnet, verifier = opus).
   Failures are dropped and logged, never silently persisted.
3. **D26 — interactive-only LLM.** All LLM work is interactive Claude Code
   subagents; Python is deterministic, independently unit-testable tooling.

**Enforcement matter matching (D53):** New enforcement items are matched to
existing wiki matters by a deterministic strong key (court docket / FTC docket or
file number) when available; otherwise by the `enforcement-matcher` subagent over
a deterministic shortlist, auto-applied only after a deterministic `confirm_match`
check (respondent token-overlap + date proximity + confidence threshold). A failed
confirm creates a new page with a `possible-duplicate-of` run-report note — a
wrong-merge is never silently committed.

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
                    enforcement/ (base, ftc, state_ag — config-driven adapters, D54)
                    transcripts.py (YouTube captions for spoken quotes, D72/D73)
                    lawbrain.py (read-only law-brain reader, PHASE-09/D2)
  pipeline/         discover, enrich, render, leg_history, refresh
                    staging.py (run-dir convention), ids.py (bill-id parsing)
                    rejects.py (scope-versioned negative cache, D82/D96)
                    verdicts.py (resumable verdict/summary application, D83)
                    extract.py + docling_text.py + docling_worker.py
                      (.text.md sidecars; Docling out-of-process, D67/D105)
                    playwright_render.py (JS re-ground pass, D78)
                    linkcheck.py (link-rot by URL family, D112)
                    tracker_gap.py (external-tracker cross-check, PHASE-29)
                    run_log.py (scan-log.md block formatter, D65)
                    enforcement.py (matter matching / confirm / merge, D53)
                    lawbrain_{keys,match,links,copy,registry,review}.py (PHASE-09)
  wiki/             schema (frontmatter models) + templates (jinja2; lawbrain:region, D63)
.claude/
  agents/           subagent prompts (classifier, summarizer, …, lawbrain-matcher)
  commands/         9 slash commands (backfill, backfill-enacted[-state], scan-states,
                    scan-enforcement, refresh, leg-history, sync-lawbrain, run)
```

## Status

Current: **v0.9.0**.

**Shipped, PHASE-01..10** — skeleton, wiki layer, federal source, LLM subagents,
legislative history, watchlist refresh, state sources via LegiScan, enforcement
actions via FTC + config-driven state-AG adapters, law-brain commentary overlay,
and the `/zwiad-run` single-entrypoint scheduling design (D65/D66).

**Shipped, PHASE-12..29** — the hardening and scale-out layer, all of it added
after this document's original draft:

- **Full-text extraction (D67, D105).** `extract-text` writes `<id>.text.md`
  sidecars via Docling, run in an isolated subprocess with a page cap because the
  native stack can abort the interpreter. Enacted-bill summaries are written
  against the extracted text rather than the API summary (D110).
- **Scope-reject ledger (D82, D96).** `wiki/.rejects/{federal,state}.json` caches
  negative classifications so no bill is re-classified for free. Entries are
  scope-versioned: a scope change **surfaces** staleness via `stale-rejects`,
  never auto-invalidates.
- **Resumable campaigns (D83, D84, D85).** Enacted-first discovery plus
  `apply-verdicts` / `apply-summaries`, batched one (jurisdiction × period) unit
  per run with a human review gate, tracked in `docs/backfill/enacted-campaign.md`.
- **Grounding-gate recall work (D76–D78, D101–D104).** Terminal-punctuation and
  dash/mojibake normalization, a Playwright re-ground pass for JS-injected quotes,
  verifier PDF staging, and Wayback recovery for pages that return 200 with an
  empty JS shell — all widening recall without loosening the D36 trust boundary.
- **Narrative gate (D106, D107).** The Legislative Journey narrative is
  verifier-checked and fail-closed dropped at render, extending D36/D40 beyond
  individual statements.
- **Link-rot detection (D112).** `check-links` probes URLs on tracked pages and
  groups dead links by URL family, built after a state legislature retired an
  entire URL scheme at once.
- **External-tracker cross-check (PHASE-29).** `tracker-gap` joins snapshots of
  the Orrick and MultiState AI-law trackers against `wiki/states` and the reject
  ledger, so coverage is measured against an outside authority rather than
  against our own discovery. See D113.

**Not implemented, by decision:** law-brain discovery / stub-minting (PHASE-11,
gated by D14, `discover=false`); any built-in scheduler (`docs/scheduling.md` —
`/zwiad-run` is designed to be triggered externally).

**Implemented but not populated:** state-AG enforcement. The adapters and config
exist; `wiki/states/*/enforcement/` is still empty and all 144 enforcement pages
are FTC. Law-brain commentary is likewise a pilot — the machinery is complete and
exactly one page carries it.
