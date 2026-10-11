# Phase 33 — Backlog: re-verify narratives + fill history gaps
Status: PENDING

## Goal
Bring every enacted page to verified, current-format legislative history and harden LegiScan pulls.

## Tasks
- [ ] Verifier-only narrative re-check for the ~75 pre-D106 narratives; failures rewritten in the new short format
- [ ] Generate the leg-history queue from wiki frontmatter (enacted without history) instead of the hand-kept doc
- [ ] Assign tiers and run the ~103 missing bills
- [ ] LegiScan on-disk response cache (bill_id + change_hash), monthly request counter, incremental candidates.json writes
- [ ] Housekeeping: sync queue doc and campaign doc

## Acceptance Criteria
- Every enacted page has a verified history or a recorded reason it has none
- LegiScan usage visible per run

## Decisions Made This Phase
