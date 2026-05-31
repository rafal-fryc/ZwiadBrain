# Phase 10 — Scheduling (`/zwiad-run` orchestration + run-log)
Status: DONE (build); operator acceptance (first live `/zwiad-run`) pending

Design: `docs/superpowers/specs/2026-05-31-phase10-scheduling-design.md`

## Goal
Expose a single, scheduler-agnostic interactive orchestration command (`/zwiad-run`) that
runs the whole pipeline across all enabled sources in one session, auto-commits per source,
and records a grep-parseable run-log — so an external runner (openclaw-like) can trigger
ZwiadBrain on a schedule later (D26: LLM work stays interactive).

## Tasks (build)
- [x] `zwiadbrain run-log` CLI verb + committed `scan-log.md` (TDD: 6 unit tests)
- [x] `.claude/commands/zwiad-run.md` orchestration runbook (sequence + per-source auto-commit + isolation + leg-history flag + summary)
- [x] `docs/scheduling.md` (scheduler-agnostic; external interactive-session runner; D26 rationale)
- [x] DECISIONS.md entries (D65, D66) — D64 reserved for the lawbrain bugfix PR
- [x] Full suite + pyright + ruff green (615 tests)

## Operator acceptance (PENDING — not a build task)
- [ ] First live `/zwiad-run` (`--dry-run`, then live): exercises all source flows + subagents against live APIs and the law brain (plan usage). Like the PHASE-09 UAT, this is an operator step, not yet exercised. Confirm: per-source auto-commit messages, `scan-log.md` block appended + committed, law brain untouched (D2), leg-history bills flagged, a re-run is a clean no-op except the new log block.

## Acceptance Criteria
- `/zwiad-run` runs the 6-step sequence (refresh → discover federal/state → enforcement → law-brain → reindex) end-to-end in one session.
- Each changed source is committed with a conventional message; unchanged sources commit nothing; a no-change run is a clean no-op except the appended run-log block.
- A `scan-log.md` block is appended and committed each run.
- The law brain is never written (D2).
- Newly-enacted bills lacking leg-history appear in the summary as a manual TODO (not auto-run).
- Full test suite + pyright + ruff stay green.

## Decisions Made This Phase
(append as you go)
- Operating model: single interactive `/zwiad-run`, externally triggered, scheduler-agnostic (collapses D41's hybrid to one interactive entrypoint).
- Commit policy: auto-commit per source (git history = audit trail); law brain read-only.
- Build: thin runbook over the 6 existing commands + one tested `run-log` helper.
- Leg-history: flag newly-enacted bills, do not auto-run.
