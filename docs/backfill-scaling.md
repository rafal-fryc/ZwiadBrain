# Backfill scaling — gap fixes before a larger campaign

Operating note from the 2026-06-08 backfill session (federal 119th + 7 states, 32 pages).
The pipeline is ready for a *staged* larger backfill; these four gaps are what make the
difference between "drive every batch by hand" and "run a smooth multi-session campaign."
Plan-token rate limits and the interactive context window are the binding constraints (by
design, D26) — every item below is about making bounded, resumable, committed slices cheap.

Priority order: 1 and 3 first (cheap, high leverage), then 2, then 4.

## 1. Resumable classification convention (verdict persistence)

**Problem.** Classification verdicts (in/out + topics per candidate) live only in the
interactive session's context. This session hit a plan rate limit mid-batch (8 of 16
classifiers died) and nearly lost verdicts to context exhaustion at ~30 states.

**Fix (convention + tiny tool).** After classifying a batch, write the verdicts to a
committed-or-staged JSON next to the run: `data/runs/<id>/verdicts.json` as
`[{ "id", "in_scope", "topics", "reason" }]`. Add a small CLI `apply-verdicts --in
candidates.json --verdicts verdicts.json` that produces `classified.json` (in-scope, with
topics applied) + `rejects.json` — replacing the ad-hoc `build_*.py` scripts used this
session. Then a rate-limit/context cutoff only loses the *unclassified* tail; rerun resumes
from `verdicts.json`.

**Effort:** small (one CLI command mirroring `render-classified`, + a `Verdict` model).
Code home: `src/zwiadbrain/cli.py` + a helper in `pipeline/`. TDD as usual.

## 2. Leaner summary handoff for in-scope-dense batches

**Problem.** States are ~90% in-scope, so nearly every candidate needs a summary. The
per-bill summarizer-subagent round-trip is the heaviest, least-automated step at scale; this
session it forced composing summaries inline to finish 6 states.

**Options (pick one when it bites):**
- (a) **Batch summarizer** — one subagent call summarizes N bills, returning `{id:
  summary}`. Cuts round-trips ~N×. Lowest-risk win.
- (b) **Defer summaries** — render in-scope pages immediately with the raw LegiScan/CRS
  summary, mark them `summary_pending`, and backfill plain-language summaries in a later
  pass. Keeps page creation fast; quality catches up asynchronously.
- (c) Accept inline composition for dense state batches (what this session did) — fine for
  small runs, doesn't scale to 50 states.

**Recommendation:** (a) batch summarizer. **Effort:** medium (new agent prompt + a render
path that accepts the `{id: summary}` map).

## 3. Push/merge cadence so the shared ledger actually helps

**Problem.** `--skip-existing` only dedups against **committed-and-present** wiki pages +
reject ledgers. Backfill content accumulating on an unpushed local branch
(`feature/initial-backfill`) means a fresh clone / another session can't benefit from the
cache.

**Fix (convention).** Push + PR + merge each slice (or batch a few) to `main` promptly so
the reject ledgers and tracked pages are shared. Treat the backfill as a campaign of small
merged increments, not one long-lived branch. No code — just discipline.

## 4. LegiScan quota monitoring at >7 states

**Problem.** 7 states used here without issue, but 50 states × (getSearchRaw + getBill per
candidate) may hit the free-tier quota (flagged D48). Untested at that scale.

**Fix.** Before fanning past ~10–15 states in a session, check LegiScan account usage; if it
binds, spread states across sessions/days or upgrade the plan. Optionally surface remaining
quota in the fetch output if the API exposes it.

## Not gaps (already adequate)

- The reject-ledger cache itself (federal date-normalized, state `change_hash`) — built,
  merged (PR #11/#12), verified live.
- Idempotent render + per-batch commit discipline.
- Federal `--max-pages` back-catalog sweep exists for depth (D81); just bound it per session.

## Suggested first larger slice (when ready)

One session ≈ one of: a federal `--max-pages` page for a chosen congress, OR ~5–8 new
states. End every session with a commit + push/merge. With gaps 1 and 3 done, the campaign
becomes: bounded fetch → classify (resumable) → enrich → render → record-rejects → commit →
merge, repeated, with the cache eliminating rework across sessions.
