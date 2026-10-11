# ZwiadBrain

A git-backed Markdown wiki of **U.S. federal and state legislation and enforcement actions**
in **AI, privacy, and cybersecurity** — built by a pipeline that pairs deterministic Python
with interactive Claude Code subagents.

The committed `wiki/**` tree **is** the product. Everything else — raw scrapes, the SQLite
index — is derived and gitignored, rebuilt from the pages themselves by `zwiadbrain reindex`.
A fresh clone is fully self-contained.

## What it does

- Track bills as they move through the legislative process, federal and state.
- Once a bill is enacted, assemble a **source-linked legislative history** in a standardized
  form — every quoted statement grounded against the page it came from.
- Track enforcement actions in the same subject areas.
- Reconcile coverage against external authorities (the Orrick and MultiState AI-law trackers),
  so a law we *don't* have is a recorded decision rather than an unnoticed gap.
- Overlay analysis from a separate, read-only **law brain** wiki — see
  [`docs/law-brain/`](docs/law-brain/).

## How it works

**Python makes zero LLM calls.** There is no `anthropic` dependency and no API key in the
data path (D26/D30) — a test, `tests/test_no_vestigial_llm_package.py`, exists to keep it that
way. All LLM work runs as **interactive Claude Code subagents** (`.claude/agents/`, 10 of them)
dispatched from a human-driven session.

Each slash command is a deterministic Python **fetch** half and a deterministic Python
**render** half, with the classification/summarization subagents in between. The two halves
exchange gitignored JSON under `data/runs/<id>/` (D27):

```
slash command (interactive Claude Code session)
  │
  ├─ fetch    deterministic Python: HTTP → models → JSON   ─┐
  │                                                          │  data/runs/<id>/*.json
  ├─ subagents  classifier / summarizer / amendment-        │  (gitignored handoff)
  │             explainer / leg-history researcher+verifier  │
  │                                                          │
  └─ render   deterministic Python: JSON → models →         ─┘
              render_page → wiki/**/*.md → reindex
```

### Three invariants

1. **Byte-identical render (D20).** `render_page(model)` is pure: unchanged input produces
   identical bytes, so a no-op re-render must leave `git status` clean. Frontmatter holds
   metadata only, except the fields that cannot be re-derived.
2. **Fail-closed grounding (D36).** A researched legislative-history statement persists only
   if it passes **both** a deterministic gate (URL returns 200, the normalized quote appears
   verbatim on the page, ≥20 chars) **and** an independent cross-model verifier
   (researcher = Sonnet, verifier = Opus). Failures are dropped and logged, never silently
   persisted.
3. **Interactive-only LLM (D26).** `claude -p` and the Agent SDK draw separate metered credit,
   so they are deliberately not used. A terminal must be open and the command triggered.

See **[`ARCHITECTURE.md`](ARCHITECTURE.md)** for the full design, **[`wiki/README.md`](wiki/README.md)**
for the page schema, and **[`DECISIONS.md`](DECISIONS.md)** for the reasoning behind every choice.

## What's in the wiki

Snapshot, counted by hand — not auto-generated:

| | Count |
|---|---|
| Federal bill pages | 9 |
| Federal enforcement pages (all FTC) | 144 |
| State bill pages | 242 |
| States covered | 36 |
| Full-text extraction sidecars (`.text.md`) | 243 |
| Pages with a source-linked legislative history | 120 |
| Recorded scope rejections (federal / state) | 1,028 / 419 |

State coverage outnumbers federal roughly 27:1 — the federal side tracks a small watchlist,
while the state side has been driven through an enacted-law backfill campaign and a
tracker cross-check.

## Setup

Python 3.12, [uv](https://docs.astral.sh/uv/):

```bash
uv sync
cp .env.example .env      # then fill in the keys below
```

Three free API keys are required: `CONGRESS_API_KEY` and `GOVINFO_API_KEY`
(both [api.data.gov](https://api.data.gov/signup/)) and `LEGISCAN_API_KEY`
([LegiScan](https://legiscan.com/legiscan)). `LAW_BRAIN_PATH` is optional and only needed for
`/zwiad-sync-lawbrain`.

Operational settings — enabled states, enforcement adapters, law-brain gates — live in
`zwiadbrain.toml`. Secrets live only in `.env`.

Gate:

```bash
uv run pytest        # 57 test modules
uv run ruff check .
uv run pyright       # strict
```

## Running it

Everything below runs inside an **interactive Claude Code session** — nothing is headless or
cron-driven (D26).

**Routine**

- `/zwiad-run [--dry-run]` — the whole pipeline in one session: refresh → federal discover →
  state discover → enforcement → law-brain → reindex, auto-committing per source and appending
  a block to `scan-log.md`. Per-source failure isolation. This is the single entrypoint an
  external runner triggers on a cadence (D65/D66).
- `/zwiad-backfill <congress> [limit]` — discover, classify, summarize, and render federal bills.
- `/zwiad-scan-states [--state <st>] [--limit <N>]` — the same for state bills, via LegiScan.
- `/zwiad-scan-enforcement [--agency <ftc|ag-slug>]` — discover, classify, match, extract, and
  render enforcement actions. Re-running it *is* the enforcement refresh (D52).
- `/zwiad-refresh` — re-fetch tracked federal and state bills, re-run subagents only where a
  cursor moved, preserve legislative history, flip out-of-scope bills to `tracking: false`
  without deleting them.

**Campaigns** (prior-year, enacted-only, one unit per run with a review gate — D84/D85;
progress in `docs/backfill/enacted-campaign.md`)

- `/zwiad-backfill-enacted <congress>`
- `/zwiad-backfill-enacted-state <state> <year>`

**Depth**

- `/zwiad-leg-history <congress/type/number | state/legiscan_bill_id>` — assemble a
  source-linked legislative history for one enacted bill. Federal
  (`/zwiad-leg-history 118/hr/2670`) or state (`/zwiad-leg-history ca/1904800`).
- `/zwiad-sync-lawbrain [--dry-run]` — attach read-only law-brain commentary and a
  `## Further Reading` section onto already-tracked pages. Commentary only; it never mints
  pages (D14).

The deterministic halves are also runnable directly — `uv run zwiadbrain --help` lists all 31
commands, including `reindex`, `tracker-gap`, `extract-text`, `check-links`, `stale-rejects`,
and `apply-verdicts`.

## Repo map

```
src/zwiadbrain/     sources/ (HTTP transport)  pipeline/ (pure logic)  wiki/ (schema + templates)
wiki/               the product — see wiki/README.md
reference/          topics.yaml taxonomy, external tracker snapshots, hand-verified corrections
docs/               operational notes, backfill campaign trackers, law-brain documentation
.claude/            agents/ (subagent prompts)  commands/ (the 9 slash commands)
tests/              57 modules; guards for D20, D26, D36, D63
```

## Status

**v0.9.0.** Shipped: the wiki layer, federal and state sources, LLM subagents, legislative
history, watchlist refresh, enforcement actions, law-brain commentary, full-text extraction,
the scope-reject ledger, resumable backfill campaigns, link-rot detection, and external-tracker
cross-check.

Known gaps, stated plainly:

- **State-AG enforcement has adapters but no content** — seven `wiki/states/*/enforcement/`
  directories are empty. The FTC side carries all 144 pages.
- **Law-brain commentary is a pilot** — the machinery works; exactly one page carries it.
- **No scheduler.** `/zwiad-run` is designed to be triggered externally; ZwiadBrain ships no
  cron or Task Scheduler wiring (`docs/scheduling.md`).
- **Law-brain discovery / stub-minting** is deliberately gated off (D14).
