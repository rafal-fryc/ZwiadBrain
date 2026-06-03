# Phase 15 — Leg-History Source Breadth · Phase C (orchestration automation)
Status: DONE

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Motivated by the Phase-A UAT, where the lane-merge + verifier-index assembly was done by hand.

## Goal
Replace the manual JSON hand-assembly between fetch → researcher lanes → verifier → render with a deterministic Python assembler and a fan-out-aware `/zwiad-leg-history`, removing the verdict↔statement index-misalignment footgun (the project's highest-stakes manual step).

## Design (decided 2026-06-02 — D74; supersedes the single-command sketch below)
Two deterministic Python steps share one merge helper, so the verifier is dispatched over a **Python-numbered** list and the indices are assigned by Python end-to-end (never hand-typed):

1. **`merge_lanes` helper** (`leg_history.py`): pure, deterministic merge of the four lane payloads in fixed order (`crec`, `hearings`, `press`, `signing`); dedups statements by `(speaker, quote)`, hearings + media by `url`; narrative from the `crec` lane only; drops a malformed lane and parse-drops a malformed item. Both CLI steps call it → byte-identical merges.
2. **`build-verifier-input` CLI**: reads `leghistory.json` (bill+spine) + `lane-{crec,hearings,press,signing}.json`; `merge_lanes`; writes `verifier-input.json` = a `subject` block + index-stamped `statements`/`related_media`. The session dispatches the verifier over THIS and writes `verifier.json`.
3. **`assemble-leg-history-input` CLI**: reads `leghistory.json` + the four lane files + `verifier.json`; `merge_lanes` again (identical order); attaches verdicts by index with the echo cross-check (fail-closed → `verified:false`); writes `leghistory-research.json` (the render-input render-leg-history already consumes). The `subject` block lives in the verifier-input, NOT the render-input (resolves the original Task-1 wording slip).

## Tasks
- [x] `merge_lanes` + `MergedResearch` in `leg_history.py`: fixed-order merge, dedup, narrative-from-crec, malformed-lane drop, item parse-drop — pure, no I/O — TDD
- [x] `build-verifier-input` CLI: run-dir in, `verifier-input.json` out (subject block + index-stamped statements/media) — TDD
- [x] `assemble-leg-history-input` CLI: run-dir + `verifier.json` in, `leghistory-research.json` out; verdicts keyed by merged index with echo cross-check, fail-closed on mismatch — TDD
- [x] Round-trip: assembler output feeds `render-leg-history` unchanged (integration test)
- [x] Update `/zwiad-leg-history` (command md): write each lane's JSON to the run dir → `build-verifier-input` → dispatch verifier over `verifier-input.json` → write `verifier.json` → `assemble-leg-history-input` → `render-leg-history` (no hand-built index arrays)
- [x] Tests (TDD): fixed-order merge, dedup, index alignment, verdict keying, malformed-lane drop, echo-mismatch fail-closed
- [x] Decision log: D74 (two-step deterministic assembler boundary; Python assembles, subagents still dispatched only from the interactive session per D26)
- [x] **Live UAT (acceptance criterion 3):** re-ran the full `/zwiad-leg-history 118/hr/2670` end-to-end via the updated command — PASSED (see below).

## Gate status (offline)
- pytest **717 passed** (+18 new in `tests/test_assemble_leg_history.py`); ruff clean; `pyright` 0 errors.
- Invariant: `ground_items` / `ground_related` / `_normalize_text` and the render-leg-history echo logic are byte-for-byte unchanged — PHASE-15 is additive (new `merge_lanes` helper + two new CLI commands + the command-md flow rewrite). render was NOT refactored.

## Live UAT result (2026-06-02 — 118/hr/2670, NDAA FY2024, PL 118-31)
Full real-pipeline run via the rewritten command, all five steps:
1. `fetch-leg-history` → spine (7 versions, 2 reports, 7 votes, 50 floor, enactment).
2. 4 researcher lanes dispatched → wrote `lane-{crec,hearings,press,signing}.json` (15 + (12 hearings/5 videos) + 14 + 4 statements).
3. `build-verifier-input` → merged to **33 statements + 5 media**, 0 lanes dropped, Python-stamped indices 0–32 / 0–4.
4. `leg-history-verifier` dispatched over `verifier-input.json` → 31 statements confirmed, **2 fail-closed (joint statement attributed to one signer)**, 5 media confirmed.
5. `assemble-leg-history-input` → bound verdicts by merged index with echo cross-check → `leghistory-research.json`.
6. `render-leg-history` (live grounding) → **28 statements grounded / 5 ground-dropped** (2 verifier-rejected + 3 live "quote not found": a wrong-page CREC URL, a `--`/em-dash mismatch, a paywalled Roll Call), **12/12 hearings, 5/5 media, narrative** — page written; `reindex` OK.

Outcome: verdict↔statement index binding was correct by construction across all 33 items (Biden's 4 passages at idx 29–32 rendered with the right quotes; the two rejected joint-statement items correctly absent) — **zero misattribution**. The on-bill / Related (Subject Matter) / Related Media split rendered as designed. The two-step assembler fully reproduced and exceeded the Phase-A manual result with no hand-built JSON. Rendered page (`wiki/federal/bills/118-hr-2670.md`) left UNCOMMITTED for operator review per the command's "do not commit" rule.

## Acceptance Criteria
- A full leg-history run requires zero hand-built JSON; the lane merge + verdict indexing is deterministic and unit-tested
- The manual merge performed in the Phase-A UAT is fully reproduced by `assemble-leg-history-input`
- Full gate green (pytest + ruff + pyright); a re-run on 118/hr/2670 via the updated command reproduces the Phase-A result

## Files to touch
- src/zwiadbrain/pipeline/leg_history.py (`merge_lanes`, `MergedResearch`) · src/zwiadbrain/cli.py (two new commands)
- .claude/commands/zwiad-leg-history.md
- new tests/test_assemble_leg_history.py

## Notes / Risks
- D26 constraint: subagents run in the interactive session, not from Python. Both new commands are pure deterministic plumbing — they must not call any LLM.
- Keep the index↔verdict echo cross-check identical in semantics to `render-leg-history`'s remap/echo logic so the two stay consistent. (render is NOT refactored this phase — feature/refactor stay separate; a future refactor can DRY the echo check onto a shared helper.)
- Two-step correctness relies on the lane files being unchanged between `build-verifier-input` and `assemble-leg-history-input`; the merge is pure/deterministic, so identical inputs → identical order.

## Decisions Made This Phase
- **D74 (2026-06-02)** — Two-step deterministic assembler (`build-verifier-input` → verifier → `assemble-leg-history-input`) over a single command, chosen by the user. Python owns the lane merge on BOTH sides of the verifier via the shared `merge_lanes` helper, so verdict indices are Python-assigned end-to-end and align by construction; the assembler still carries the echo cross-check as fail-closed defense in depth. The `subject` block belongs to the verifier-input, not the render-input (resolves the original Task-1 wording).
