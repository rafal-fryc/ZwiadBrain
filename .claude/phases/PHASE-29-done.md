# Phase 29 — Tracker cross-check gap fill (Orrick + MultiState)
Status: DONE

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
- [x] Commit the gap as a reviewable artifact — `docs/backfill/tracker-gap-2026-07.json`
- [x] Build `tracker-gap` + `fetch-tracker-candidates` (resolve bill number → LegiScan
      `bill_id` via `getSessionList` + `getMasterList`, enrich via `getBill`)
- [x] Session-year hints from tracker links + `reference/tracker-corrections.yaml`
- [x] Resolve every gap bill: **182 / 182 staged, zero unresolved**
      (`data/runs/tracker/<st>/` per state, merged into `data/runs/tracker-all/`)
- [x] **Classify the gap** — 177/177 resolved: 31 in, 146 out, 38 documented overrides (c4a6aeb)
- [x] Resolve the 94 citation-only rows — 32 enacted classified, 10 in / 22 out (4cc00ec) (42 already mapped to a bill number from the
      tracker's own link; 32 statute-text, 16 unparsed, 4 administrative/local)
- [x] Run the rest of the procedure: apply-verdicts → record-rejects → render → extract
      → summarize → re-render → reindex
- [x] Record every unit in `docs/backfill/enacted-campaign.md` with counts and reject reasons

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
- 2026-07-24 — The join ignores the session year (Orrick rows carry only an effective date).
  Year-agnostic matches whose wiki year disagrees are reported, not trusted.
- 2026-07-24 — The number resolver never guesses: a number enacted in two sessions with no
  year hint to separate them is reported `ambiguous` rather than resolved to the newest.
- 2026-07-24 — Tracker data errors and session-year pins live in
  `reference/tracker-corrections.yaml`, each with its reasoning; a stale entry is a hard
  error so snapshot drift surfaces immediately.

- 2026-07-24 — **User decision: override per-bill under D86/D91**, not a `topics.yaml`
  change. No `scope_version` bump, so the 252 existing rejects stay current. Every
  override records the classifier's verdict and the reason it was reversed.
  Note this is a per-bill judgment, NOT a blanket rule by tracker topic: CT HB 5312 is
  tagged "AI Intimate Images" but imposes a covered-platform takedown-request duty, which
  is company-facing and genuinely in scope. The tracker's tag narrows attention; the
  operative text decides.

## RESOLVED — classifier verdicts vs. established precedent
First 12 classifications: 5 in-scope, and **4 of those 5 are categories the campaign log
consistently OVERRIDES to out-of-scope** — AL HB 172, AZ SB 1359, CA AB 2839 (election
deepfake disclosure, D91: NH HB 1596, VT S 23, CA AB 2355, LA HB 459/639, ME LD 517 all
rejected) and AR HB 1877 (AI-CSAM criminal, per TN HB 2163 and LA SB 110 overrides; CA
SB 926 deliberately not flipped).

Roughly 63 of the 182 carry those tracker tags, so the choice is material and should be
made once, up front, rather than 63 times by hand:
1. Apply the documented D86/D91 overrides per-bill (matches current practice; the
   classifier's verdict is recorded and reversed with a stated reason).
2. Encode the rule in `topics.yaml` as a disqualifier — cleaner and self-consistent, but a
   `scope_version` bump that makes every existing reject stale for review (D96).
3. Take the categories in scope — a real scope expansion, since both trackers treat them
   as AI law.

**Chosen: (1).** See the decision entry above.

## Note on PHASE-26
PHASE-26 (enacted-laws backfill campaign) is still marked ACTIVE though
`docs/backfill/enacted-campaign.md` records its state campaign as complete. Confirm whether it
should be renamed `PHASE-26-done.md` before this phase proceeds past the tooling step.

- 2026-10-11 — Closed. Open accuracy items (33 REVIEW-flagged rejects: empty extractions,
  title-only riders, thin summaries, health-AI re-checks) carry into PHASE-30's regression set.
