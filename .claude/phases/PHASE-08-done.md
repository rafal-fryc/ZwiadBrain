# Phase 08 — Enforcement actions (FTC + state AGs)
Status: DONE — implementation complete (v0.8.0); merged to main via PR #3 (cfd71a2); live FTC UAT validated; 2 enforcement wiki pages shipped

> Full design: docs/superpowers/specs/2026-05-29-phase08-enforcement-actions-design.md
> Full plan:   docs/superpowers/plans/2026-05-29-phase08-enforcement-actions.md
> Decisions:   D52 (discovery-driven, re-scan = refresh), D53 (two-tier matter
>              matching + deterministic confirm), D54 (generic config-driven AG
>              adapter + failure isolation), D55 (separate enforcement rubric/subagents,
>              shared taxonomy/model/render/CLI), D56 (EnforcementAction prose persists
>              to frontmatter so consolidation is monotonic).

## Goal
Enforcement actions (FTC + the 7 priority-state AGs) become first-class tracked wiki
pages via a discovery-driven `/zwiad-scan-enforcement` command, with two-tier matter
matching that consolidates multi-item matters (complaint → settlement) onto one page.

## Tasks
(from docs/superpowers/plans/2026-05-29-phase08-enforcement-actions.md; executed via
subagent-driven development — fresh implementer per task + two-stage review)
- [x] T1  — models: EnforcementDevelopment + EnforcementAction.developments
- [x] T2  — templates: Developments section + frontmatter round-trip
- [x] T3  — ids: parse_strong_key + build_enforcement_id
- [x] T4  — pipeline/enforcement.py: pure matching/confirm/merge helpers
- [x] T5  — sources/enforcement/base.py: EnforcementSource + feed/HTML helpers
- [x] T6  — sources/enforcement/ftc.py: FTCSource
- [x] T7  — sources/enforcement/state_ag.py: generic StateAGSource + failure isolation
- [x] T8  — config: EnforcementSettings + zwiadbrain.toml entries
- [x] T9  — cli: fetch-enforcement-candidates
- [x] T10 — cli: render-enforcement (build/consolidate + deterministic confirm)
- [x] T11 — topics.yaml enforcement rubric + 3 subagents
- [x] T12 — slash command /zwiad-scan-enforcement
- [x] T13 — DECISIONS D52-D56 + ARCHITECTURE + PLAN
- [x] T14 — quality gate + version bump 0.8.0
- [x] T15 — live UAT (FTC validated on real data; see results below)

## Acceptance Criteria
- [x] FTC RSS → `EnforcementAction` page under `wiki/federal/enforcement/`, byte-identical
  re-render (D20) — validated on a REAL FTC item in UAT; state-AG `states/<st>/enforcement/`
  routing + the rss/html adapter validated via fixtures (T7) — no state AG enabled live (see UAT).
- [x] Strong-key consolidation + no-strong-key `enforcement-matcher` + deterministic confirm
  fail-safe (D53) — validated by T10 unit tests (new matter / strong-key consolidate /
  llm-failing-confirm→new-page / idempotent / omitted-prose preserved). Real docket-sharing
  consolidation not exercised (no such pair in the live window).
- [x] Generic state-AG adapter handles `kind=rss` and `kind=html`; one broken source is
  isolated and does not abort the run (D54) — fixtures (T7) + live (CA OAG 404 isolated cleanly).
- [x] `enforcement-classifier` applies the rubric; `enforcement-extractor` fills fields +
  prose + development summary (D55) — both validated on real FTC data in UAT.
- [x] `/zwiad-scan-enforcement` renders real FTC pages; re-scan is idempotent — validated
  (real item rendered to a throwaway wiki; byte-identical re-render). Populating the
  COMMITTED wiki is the operator's interactive run (D26; "leave for review").
- [x] ruff + pyright (strict) + pytest all green (464 passing); v0.8.0; DECISIONS D52–D56 logged.

## Live UAT Results (2026-05-29)
- **FTC feed validated** against `https://www.ftc.gov/feeds/press-release.xml` — returned 5
  real recent press releases; article text extracted; candidate structure correct;
  forward-from-now window works on real dates.
- **Bug found + fixed (6e544c5):** default httpx User-Agent → HTTP 403 from FTC (and other
  `.gov` bot filters). Added a browser User-Agent to the enforcement HTTP clients; feed then
  returns 200. This blocked ALL enforcement HTTP before the fix.
- **Rubric validated on real data:** 5/5 defensible verdicts — Cox Media "Active Listening"
  AI + both TAKE IT DOWN Act items IN (ai/privacy); Cliq (payment) + Shutterstock
  (subscription) OUT. Two rubric refinements applied (e2958aa): action-type list now includes
  warning letters / enforcement-commencement; deceptive-advertising disqualifier carves out
  misrepresentations that concern an AI/data/privacy/security capability.
- **Extractor + render validated on real data:** the Cox Media item extracted cleanly
  (dual deceptive-AI + false-consent prongs, penalties, statutes, status=proposed) and
  rendered to a valid page with prose persisted to frontmatter (D56 confirmed live) and a
  byte-identical idempotent re-render (D20).
- **Failure isolation validated live:** CA OAG `/feed` 404 was isolated (logged, 0 staged, no crash).
- **CA OAG config corrected (e2958aa):** no public RSS + listing 404 → disabled pending
  per-site tuning. All 7 state AGs are now `enabled = false` awaiting selector tuning (D54).

## Remaining (operator, not implementation)
- Run `/zwiad-scan-enforcement --agency ftc` in an interactive session to populate the
  committed `wiki/federal/enforcement/` (D26; review before committing).
- Tune each state AG's URL + html `item_selector` against its live site and flip
  `enabled = true` per state during the rollout (D54).
- Minor follow-up: cap the respondent slug length in `build_enforcement_id` (a multi-entity
  respondent produced a long fallback id — valid + stable, but unwieldy).

## Decisions Made This Phase
D52–D56 logged in `DECISIONS.md` (see header). Refinements during execution:
- D53 hardened: when a match's date is absent, `confirm_match` requires a stronger
  respondent overlap (0.6) since date proximity can't ground it.
- D54 extended: failure isolation at BOTH the per-source `discover` and per-article
  `fetch_text` levels.
- D56 added: EnforcementAction prose persists to frontmatter (type-aware), unlike Bill,
  so consolidation preserves an earlier development's prose.
