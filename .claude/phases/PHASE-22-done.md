# Phase 22 — Discovery back-catalog offset pagination + wiki-dedup (D33 / D44 deferred)
Status: DONE

> Independent of the leg-history thread. D44 fixed v1 as "forward-from-now": discovery
> saw only the newest-updated ~250 bills, so a topical bill not recently updated in a
> historical congress stayed unreachable. Operator chose pagination + wiki-dedup.

## Goal
Add opt-in offset pagination to federal discovery so a historical congress can be swept
past the newest-250 window, and keep a re-sweep idempotent — without changing the
default forward-from-now behaviour.

## Scope — RESOLVED (operator, 2026-06-08)
Pagination + wiki-dedup. Investigation found discovery does NOT dedup against the wiki
today (that is downstream in the subagent layer), so the "idempotent against the seen
store" criterion was implemented as a NEW deterministic `--skip-existing` step. Logged D81.

## What shipped
- `CongressSource.discover(max_pages=1)` — opt-in bounded offset sweep: default 1 keeps the
  exact single-request behaviour (no `offset` param); >1 accumulates successive offset pages,
  dedups by `native_id`, stops at max_pages / reported total / short page, logs the remainder.
- `max_pages` added to the `Source` protocol (LegiScan + test fakes accept-and-ignore it,
  the `congress` precedent) — keeps the protocol-signature-sync test green.
- `discover.filter_unseen(candidates, known_ids)` + `cli._existing_federal_bill_ids(wiki)`.
- `fetch-candidates` flags: `--max-pages` (sweep), `--skip-existing` + `--wiki` (drop bills
  already tracked, before enrich/probe). Both default off.

## Tasks
- [x] Opt-in offset pagination over a congress (bounded, default off)
- [x] Idempotent re-runs: `--skip-existing` drops already-tracked bills (no re-classify)
- [x] Within-sweep dedup by `native_id`; guardrails (max_pages cap, _MAX_PROBE) + remainder log
- [x] TDD: 5 congress pagination (single-page-unchanged / follows-offsets / cross-page dedup /
      caps-at-max-pages+warns / stops-when-exhausted) + 3 `filter_unseen` + 2 CLI
      (`--skip-existing` drops tracked, `--max-pages` threads through)
- [x] Decision log entry (D81, supersedes the D44 deferral)
- [x] Gate: pytest 785 (+10), ruff clean, pyright at the unchanged 20-baseline

## Acceptance Criteria
- [x] A bounded historical sweep discovers bills outside the newest-250 window (max_pages>1)
- [x] Default behaviour unchanged when the flags are off (single request, no offset param)
- [x] Re-runs do not re-stage already-seen bills (`--skip-existing` + filter_unseen)
- [x] Full gate green

## Notes
- `--skip-existing` only sees COMMITTED wiki pages; two uncommitted sweeps in one session can
  still re-stage (acceptable — the downstream subagent layer also de-dups).
- This phase is the federal-discovery subsystem, not leg-history; it rides the same
  `feature/leg-history-phase-e` branch as PHASE-18-21 but is a separable concern.

## Decisions Made This Phase
- **D81 (2026-06-08)** — Opt-in bounded offset sweep + opt-in wiki-dedup on fetch-candidates;
  `max_pages` on the Source protocol. Full rationale in DECISIONS.md D81.
