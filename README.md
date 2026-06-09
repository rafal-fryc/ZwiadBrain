# ZwiadBrain

An LLM-driven wiki and agent system for **tracking U.S. federal and state legislation and enforcement actions** in the areas of **AI, privacy, and cybersecurity**.

## Goal

- Identify and track bills as they move through the legislative process.
- Once a bill is enacted, assemble its legislative history in a standardized form.
- Track related enforcement actions in the same subject areas.
- Organize everything into an LLM wiki: per-bill pages covering what the bill is about, how it changed via amendments, and the legislative history that helps interpret it.
- Keep the corpus current via a scheduled job that runs headless source detection a few times per week; the LLM enrichment pass that turns detected changes into pages runs in an interactive Claude Code session (see DECISIONS.md D41).

## How it works

ZwiadBrain builds a git-backed Markdown wiki: one validated page per tracked
federal bill. All LLM work runs as **interactive Claude Code subagents** —
Python is deterministic, independently-testable tooling and makes no LLM calls
(DECISIONS.md D26/D30). Each slash command pairs a deterministic Python "fetch"
half with a "render" half, exchanging JSON under `data/runs/<id>/`, with the
classification/summarization subagents in between.

See **`ARCHITECTURE.md`** for the full current-state design.

## Running it

These run inside an **interactive Claude Code session** (a terminal must be open
and the command triggered — nothing is headless or cron-driven, D26):

- `/zwiad-backfill` — discover, classify, summarize, and render federal bills.
- `/zwiad-backfill-enacted <congress>` / `/zwiad-backfill-enacted-state <st> <year>` —
  backfill **enacted-only** laws from prior years (one Congress / state-session per run,
  with a review gate), tracked in `docs/backfill/enacted-campaign.md` (D84/D85).
- `/zwiad-leg-history <congress/type/number>` — assemble a source-linked
  legislative history for one enacted bill (e.g. `/zwiad-leg-history 118/hr/2670`).
- `/zwiad-refresh` — re-fetch tracked bills, re-run subagents only where a bill
  changed, preserve legislative history, flip out-of-scope bills without
  deleting them.

The underlying deterministic steps are also runnable directly as CLI commands
(`python -m zwiadbrain --help`): `fetch-candidates` / `render-classified`,
`fetch-enacted-candidates` / `fetch-state-enacted-candidates` (enacted-only discovery),
`fetch-leg-history` / `render-leg-history`, `fetch-refreshable` /
`render-refreshed`, plus `reindex` and `backfill`.

## Status

Shipped through **PHASE-06** (v0.6.0): skeleton, wiki layer, federal source,
LLM subagents, legislative history, watchlist refresh. State sources (LegiScan),
enforcement actions (FTC + state AGs), law-brain commentary, and scheduling are
planned but not yet implemented — see `ARCHITECTURE.md` for the current scope and
`DECISIONS.md` for the reasoning.
