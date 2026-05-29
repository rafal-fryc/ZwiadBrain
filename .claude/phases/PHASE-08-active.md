# Phase 08 — Enforcement actions (FTC + state AGs)
Status: ACTIVE

> Full design: docs/superpowers/specs/2026-05-29-phase08-enforcement-actions-design.md
> Full plan:   docs/superpowers/plans/2026-05-29-phase08-enforcement-actions.md (pending writing-plans)
> Decisions:   D52 (discovery-driven, re-scan = refresh), D53 (two-tier matter
>              matching + deterministic confirm), D54 (generic config-driven AG
>              adapter + failure isolation), D55 (separate enforcement rubric/subagents,
>              shared taxonomy/model/render/CLI).

## Goal
Enforcement actions (FTC + the 7 priority-state AGs) become first-class tracked wiki
pages via a discovery-driven `/zwiad-scan-enforcement` command, with two-tier matter
matching that consolidates multi-item matters (complaint → settlement) onto one page.

## Tasks
- [ ] Populated from the implementation plan (writing-plans).

## Acceptance Criteria
- [ ] An FTC RSS/HTML fixture maps to an `EnforcementAction` page under
  `wiki/federal/enforcement/`; a state-AG fixture under `wiki/states/<st>/enforcement/`;
  byte-identical re-render (D20).
- [ ] Strong-key (docket / FTC number) consolidation folds a later development onto the
  existing matter page; a no-strong-key item is matched via the `enforcement-matcher`
  subagent + deterministic confirm, failing safe to a new page (D53).
- [ ] The generic state-AG adapter handles both `kind=rss` and `kind=html`; one broken
  source is isolated and does not abort the run (D54).
- [ ] `enforcement-classifier` applies the enforcement rubric block in topics.yaml;
  `enforcement-extractor` fills structured fields + prose + a development summary (D55).
- [ ] `/zwiad-scan-enforcement` renders real FTC pages in live UAT; re-scan is idempotent.
- [ ] ruff + pyright (strict) + pytest all green; version bumped; DECISIONS D52–D55 logged.

## Decisions Made This Phase
(append as work proceeds — D52–D55 drafted in the design spec §12)
