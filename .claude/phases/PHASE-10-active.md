# Phase 10 — Scheduling (`/zwiad-run` orchestration + run-log)
Status: ACTIVE

Design: `docs/superpowers/specs/2026-05-31-phase10-scheduling-design.md`

## Goal
Expose a single, scheduler-agnostic interactive orchestration command (`/zwiad-run`) that
runs the whole pipeline across all enabled sources in one session, auto-commits per source,
and records a grep-parseable run-log — so an external runner (openclaw-like) can trigger
ZwiadBrain on a schedule later (D26: LLM work stays interactive).

## Tasks
- [ ] `zwiadbrain run-log` CLI verb + committed `scan-log.md` (TDD: helper unit-tested)
- [ ] `.claude/commands/zwiad-run.md` orchestration runbook (sequence + per-source auto-commit + isolation + leg-history flag + summary)
- [ ] `docs/scheduling.md` (scheduler-agnostic; external interactive-session runner; D26 rationale)
- [ ] DECISIONS.md entries for the 4 decisions captured in the design
- [ ] Interactive dry-run validation of `/zwiad-run` (D26 — runbook validated interactively, not by unit tests)

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
