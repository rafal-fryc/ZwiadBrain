# Phase 23 — Federal enacted discovery
Status: ACTIVE

## Goal
Add enacted-only federal discovery (`CongressSource.discover_laws` over `/law/{congress}/pub` + a `fetch-enacted-candidates` CLI) so the prior-years backfill never enriches a non-enacted bill.

## Tasks
- [ ] Task 1 — `/law/{congress}/pub` discovery fixture + live shape confirmation
- [ ] Task 2 — extract shared `_sweep_candidates` from `discover` (refactor, no behavior change)
- [ ] Task 3 — `CongressSource.discover_laws`
- [ ] Task 4 — `fetch-enacted-candidates` CLI (recall default, `--classify-all`, `--skip-existing`)
- [ ] Task 5 — full quality gate + live smoke + ARCHITECTURE note

## Acceptance Criteria
- `discover_laws(congress)` returns enacted-public-law candidates in `congress/type/number` id format.
- `fetch-enacted-candidates --congress N` stages only topical enacted laws (recall default); `--classify-all` stages all; `--skip-existing` honors wiki + reject ledger.
- Existing 79+ tests stay green; new source + CLI tests pass; ruff + pyright clean.
- Live smoke against the 118th confirms the real `/law/{congress}/pub` shape; staged bills all have `enacted: true`.

## Decisions Made This Phase
(append as you go)

## Plan
docs/superpowers/plans/2026-06-08-enacted-backfill-phase-23-federal-discovery.md
