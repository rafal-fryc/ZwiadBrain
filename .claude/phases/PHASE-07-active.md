# Phase 07 — State legislation via LegiScan (backfill + refresh)
Status: ACTIVE

> Full design: docs/superpowers/specs/2026-05-29-phase07-state-legislation-design.md
> Full plan:   docs/superpowers/plans/2026-05-29-phase07-state-legislation.md
> Decisions:   D48 (state id + legiscan_bill_id), D49 (50-state scope),
>              D50 (query API + change_hash cursor), D51 (error/redaction).

## Goal
State bills become first-class tracked pages: LegiScan-backed discovery/classify/
render (the /zwiad-scan-states backfill) plus change_hash incremental refresh folded
into /zwiad-refresh. Built for 50 states, validated on the priority 7.

## Tasks
- [ ] T1  — _redact: mask key= as well as api_key=
- [ ] T2  — models: add Bill.legiscan_bill_id
- [ ] T3  — ids: build_state_bill_id + format_state_bill_number
- [ ] T4  — LegiScanSource transport + error/redaction
- [ ] T5  — LegiScanSource.fetch (getBill -> Bill mapping)
- [ ] T6  — LegiScanSource.discover (getSearchRaw)
- [ ] T7  — LegiScanSource.change_hashes (getMasterListRaw)
- [ ] T8  — config: require_legiscan_api_key
- [ ] T9  — refresh: detect_state_refreshable
- [ ] T10 — cli: fetch-state-candidates
- [ ] T11 — cli: fetch-state-refreshable
- [ ] T12 — slash commands: /zwiad-scan-states (new) + /zwiad-refresh (extend)
- [ ] T13 — DECISIONS.md D48-D51 + ARCHITECTURE/PLAN/toml updates
- [ ] T14 — quality gate + version bump 0.7.0 + PHASE-07 done
- [ ] T15 — live UAT (CA priority states)

## Acceptance Criteria
- A LegiScan getBill fixture maps to a Bill with id `ca-2023-sb-362`, jurisdiction
  `US-CA`, legiscan_bill_id set, byte-identical re-render (D20).
- getSearchRaw discovery yields relevance-ordered bill_id candidates; getMasterListRaw
  change_hash diffing re-fetches only changed bills.
- /zwiad-scan-states renders real CA pages; /zwiad-refresh covers federal + state in
  one run.
- ruff + pyright (strict) + pytest all green; v0.7.0 tagged.
- DECISIONS.md carries D48-D51.

## Decisions Made This Phase
(append as you go)
