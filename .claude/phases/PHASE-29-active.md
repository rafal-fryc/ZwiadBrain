# Phase 29 — Tracker cross-check gap fill (Orrick + MultiState)
Status: ACTIVE

## Goal
Close the coverage gap between ZwiadBrain and the two external AI-law trackers snapshotted in
`reference/orrick-ai-tracker-2026-07.yaml` — every tracked law either has a wiki page or a
scope-stamped entry in the reject ledger, so the next tracker cross-check starts clean.

## Scope
- **Orrick US AI Law Tracker** — 244 rows: 148 bill-numbered laws + 96 statute-citation-only rows.
- **MultiState AI Legislation Tracker** (2025+2026 enacted, appended to the same file) — 156 rows.
- Cross-check verdict (2026-07-24): **38 already tracked**, **29 already scope-rejected**,
  **188 in the true gap** across 45 states, plus **94 unique citation-only rows** to resolve.

## Tasks
- [x] Deterministic cross-check joining both source lists against `wiki/states` and
      `wiki/.rejects/state.json` on `(state, chamber-class, number)`, session year ignored
- [ ] Commit the gap as a reviewable artifact under `docs/backfill/`
- [ ] Build `fetch-tracker-candidates` — resolve (state, bill number) → LegiScan `bill_id`
      via `getSessionList` + `getMasterList`, enrich via `getBill`, honour `--skip-existing`
- [ ] Resolve the 94 citation-only rows to an originating bill (or mark as administrative
      regulation / already-tracked-under-its-bill-number) and fold survivors into the targets
- [ ] Run the standard state procedure per batch: classify → apply-verdicts → record-rejects
      → render → extract → summarize → re-render → reindex
- [ ] Record every unit in `docs/backfill/enacted-campaign.md` with counts and reject reasons

## Acceptance Criteria
- Every bill-numbered tracker law is tracked, scope-rejected, or logged as unresolvable
  with a stated reason.
- Every citation-only row is resolved to a bill, to an administrative regulation (out of the
  LegiScan pipeline by construction), or to an already-tracked law.
- Zero non-enacted bills ingested — both trackers list enacted law only.
- Classifier overrides follow existing precedent (D86 government-use, D91 election-actor,
  person-facing criminal deepfake/CSAM) and are documented per unit, not applied silently.

## Known scope tension (flagged, not resolved)
Orrick's topic tags on the gap are dominated by **AI CSAM (21) + AI Intimate Images (21) +
AI in Political Advertising (13) + AI in Government (8)**. Established ZwiadBrain precedent puts
these OUT: D86 (government own-use), D91 (election-actor), and the documented person-facing
criminal overrides (TN HB 2163, LA SB 110, LA HB 639, ME LD 517; CA SB 926 deliberately not
flipped). Expect a low in-scope yield and a material number of classifier overrides. The point
of running them anyway is the **negative cache** — an unrecorded gap re-surfaces on every future
tracker cross-check.

## Decisions Made This Phase
(append as you go)

- 2026-07-24 — User decision: run **all** gap bills through the classifier rather than
  pre-filtering by tracker topic, so the reject ledger permanently absorbs the gap.
- 2026-07-24 — User decision: resolve the citation-only rows **in this campaign**, not deferred.

## Note on PHASE-26
PHASE-26 (enacted-laws backfill campaign) is still marked ACTIVE though
`docs/backfill/enacted-campaign.md` records its state campaign as complete. Confirm whether it
should be renamed `PHASE-26-done.md` before this phase proceeds past the tooling step.
