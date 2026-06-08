# Phase 24 — State enacted discovery
Status: PENDING

## Goal
Add prior-session, enacted-only state discovery via LegiScan (`list_sessions` + `list_session_enacted` over `getMasterListRaw(id=session_id)` filtered to `status==4`) plus a `fetch-state-enacted-candidates` CLI, with free title+description recall from the masterlist.

## Tasks
- [ ] Session-list fixture + live confirmation that `getMasterListRaw?id=<session_id>` carries per-row `status` and selects a prior session
- [ ] `LegiScanSource.list_sessions` (+ `Session` dataclass)
- [ ] `LegiScanSource.list_session_enacted(session_id)` — keep `status==4`, return candidates with title+description
- [ ] `fetch-state-enacted-candidates --state <st> --year <YYYY>` CLI (free title+description recall, `--classify-all`, `--skip-existing` parity)
- [ ] Post-enrich non-law (ceremonial/memorial resolution) guard
- [ ] Full gate + live smoke

## Acceptance Criteria
- `list_sessions()` maps a year range to prior-session ids; `list_session_enacted` returns only enacted (`status==4`) bills for a session.
- `fetch-state-enacted-candidates --state ca --year 2023` stages topical enacted CA laws from the right session; `--skip-existing` honors wiki + state reject ledger.
- Existing tests stay green; new tests pass; ruff + pyright clean.

## Acceptance gate
Do not start until PHASE-23 is DONE and user-approved.
