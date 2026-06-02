# Phase 15 — Leg-History Source Breadth · Phase C (orchestration automation)
Status: PENDING

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Motivated by the Phase-A UAT, where the lane-merge + verifier-index assembly was done by hand.

## Goal
Replace the manual JSON hand-assembly between fetch → researcher lanes → verifier → render with a deterministic Python assembler and a fan-out-aware `/zwiad-leg-history`, removing the verdict↔statement index-misalignment footgun (the project's highest-stakes manual step).

## Tasks
- [ ] New deterministic CLI `assemble-leg-history-input`: reads the run dir + each researcher lane's JSON + the verifier JSON (as files); merges lanes in fixed order (crec, hearings, press, signing); dedups statements (speaker+quote) and hearings/media (url); builds the render-input with a `subject` block and `verdicts` keyed by merged index; validates shapes; writes `leghistory-research.json` — NO LLM calls — TDD
- [ ] Update `/zwiad-leg-history` (command md): after dispatching the lanes + verifier, write each lane's JSON and the verifier JSON to the run dir, then call `assemble-leg-history-input` instead of hand-building the index array
- [ ] Carry the verifier echo cross-check + index contract through the assembler (fail-closed on mismatch), matching what `render-leg-history` already enforces
- [ ] Tests (TDD): fixed-order merge, dedup, index alignment, verdict keying, malformed-lane drop, echo-mismatch fail-closed
- [ ] Decision log: deterministic assembler boundary (Python assembles; subagents still dispatched only from the interactive session per D26)

## Acceptance Criteria
- A full leg-history run requires zero hand-built JSON; the lane merge + verdict indexing is deterministic and unit-tested
- The manual merge performed in the Phase-A UAT is fully reproduced by `assemble-leg-history-input`
- Full gate green (pytest + ruff + pyright); a re-run on 118/hr/2670 via the updated command reproduces the Phase-A result

## Files to touch
- src/zwiadbrain/cli.py (new `assemble-leg-history-input`) · src/zwiadbrain/pipeline/leg_history.py (merge/dedup helpers if extracted)
- .claude/commands/zwiad-leg-history.md
- tests/test_cli_leg_history.py (or a new tests/test_assemble_leg_history.py)

## Notes / Risks
- D26 constraint: subagents run in the interactive session, not from Python. The assembler is pure deterministic plumbing — it must not call any LLM.
- Keep the index↔verdict contract identical to `render-leg-history`'s remap/echo logic so the two stay consistent.

## Decisions Made This Phase
(append as you go)
