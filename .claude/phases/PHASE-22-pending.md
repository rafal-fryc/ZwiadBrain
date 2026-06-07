# Phase 22 — Discovery back-catalog offset pagination (D33 / D44 deferred)
Status: PENDING

> Independent of the leg-history thread. D44 fixed v1 as "forward-from-now":
> discovery recalls the newest-updated 250 bills + a policyArea probe, so a topical
> bill not recently updated in a historical congress stays unreachable. D33/D44
> named full back-catalog offset pagination as the deferred follow-up.

## Goal
Add opt-in offset pagination to federal discovery so a historical congress can be
swept past the newest-250 window, closing the known recall gap — without changing
default forward-from-now behavior.

## Tasks
- [ ] Offset-paginated recall over a congress (bounded, opt-in flag/param; default off)
- [ ] Idempotent against the existing cursor/seen store (no duplicate re-classification)
- [ ] Rate-limit / page-cap guardrails; log what was and wasn't swept (no silent caps)
- [ ] TDD with recorded Congress.gov pagination fixtures
- [ ] Decision log entry (supersedes the D44 deferral)

## Acceptance Criteria
- A bounded historical sweep discovers bills outside the newest-250 window
- Default behavior unchanged when the flag is off
- Re-runs do not re-classify already-seen bills
- Full gate green

## Notes / Risks
- Recall vs cost: deeper pagination = more API calls + more classifier dispatches.
  Keep it opt-in and bounded; surface the coverage boundary in the run log.
