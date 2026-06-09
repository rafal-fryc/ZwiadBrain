# Phase 24 — State enacted discovery
Status: DONE

## Goal
Add prior-session, enacted-only state discovery via LegiScan (`list_sessions` + `list_session_enacted` over **`getMasterList(id=session_id)`** filtered to `status==4`) plus a `fetch-state-enacted-candidates` CLI, with free title+description recall from the masterlist.

## Tasks
- [x] Task 1 — `getSessionList` + `getMasterList` fixtures + live confirmation (getMasterList carries status/title/description; Raw does not)
- [x] Task 2 — `Session` dataclass + `LegiScanSource.list_sessions`
- [x] Task 3 — `LegiScanSource.list_session_enacted(session_id)` — keep `status==4`, carry title+description+change_hash
- [x] Task 4 — extend `keyword_filter` to match title+summary (enables state recall on description)
- [x] Task 5 — `fetch-state-enacted-candidates --state <st> --year <YYYY>` CLI (free recall, `--classify-all`, `--skip-existing` parity)
- [x] Task 6 — full gate + live smoke + ARCHITECTURE note

## Acceptance Criteria
- `list_sessions()` maps a year to the covering session id(s); `list_session_enacted` returns only enacted (`status==4`) bills, carrying title+description+change_hash.
- `fetch-state-enacted-candidates --state ca --year 2019` stages topical enacted CA laws from the right session; `--classify-all` stages all enacted; `--skip-existing` honors wiki + state reject ledger.
- Existing suite stays green; new tests pass; ruff + pyright clean; live smoke confirms the real getSessionList/getMasterList path.

## Decisions Made This Phase
- **`getMasterList`, not `getMasterListRaw`** — live probe (2026-06-08) showed Raw carries only bill_id/number/change_hash; the non-Raw getMasterList carries status/title/description per row (CA 2019-20 session 1624: 5,423 rows, 1,626 status==4). Spec §4.2/§4.4/§15 corrected accordingly.
- State recall reuses `keyword_filter` extended to match title+summary (description on `Candidate.summary`); federal title-only behaviour preserved (federal candidates have no summary).
- No post-enrich ceremonial-resolution guard built — `status==4` already excludes non-passed items, and a chaptered resolution is a genuine enactment.

## Reviews
- Tasks 2+3, 4, 5: independent spec + code-quality review — Approved (with cheap follow-ups applied: empty-case tests, year-defaulting comment, docstring clarity, multi-session dedup, --skip-existing + no-session-error tests).
- Live smoke (CA 2019, recall path): 5 staged bills, all enacted + US-CA + on-topic (CCPA AB-25/713/874, SSN AB-499, cybersecurity AB-1043).
- Final whole-phase review (opus, base b945ac4 → 40a9e2c): Ready to merge; 843 tests pass, ruff + pyright clean; no Critical/Important. Minor (optional follow-up): a test exercising the multi-session dedup branch.

## Plan
docs/superpowers/plans/2026-06-08-enacted-backfill-phase-24-state-discovery.md

## Acceptance gate
PHASE-23 is DONE (PR #14) and the user approved starting PHASE-24.
