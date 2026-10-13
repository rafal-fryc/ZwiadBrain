# Phase 34 — Law-brain sync gaps
Status: ACTIVE

## Goal
Make `/zwiad-sync-lawbrain` settle every page it sees (keyless, collision, operator-resolved), refresh linked commentary when the law brain changes, parse the law brain once per run, and make malformed law-brain pages diagnosable.

## Tasks
- [x] 1. Render parses the law brain once per run (refactor, no behavior change)
- [x] 2. Malformed law-brain page warning names the failing front-matter line; fetch reports a malformed count
- [x] 3. Keyless pages: capped/floored shortlist (config), auto `not_in_scope` for empty shortlists, shortlist-aware decision hash, skill stages `not_in_scope` + `page_keys`
- [x] 4. Operator accept/reject record the real decision hash; override scoped to its target; accepted overrides re-emitted by fetch so they attach
- [x] 5. Linked pages re-emitted as `refresh` when the law-brain `content_hash` differs from the stored commentary
- [x] 6. Collisions staged by the skill and written to the review queue (one line per target); accept prunes siblings
- [ ] 7. Re-run `/zwiad-sync-lawbrain` (dry-run, then apply) and report counts
- [x] DECISIONS.md entries for shortlist cap, keyless hashing, collision review flow

## Acceptance Criteria
- `uv run pytest -q` and `uv run pyright` clean after each step
- Render calls `LawBrainReader.pages()` once per run
- A re-fetch right after an applied sync stages ~0 candidates, apart from pending collisions and malformed pages
- Accepting a collision line attaches commentary on the next run without re-proposing the page
- An edited law-brain page re-copies onto its linked target; an unchanged one leaves `git status` clean

## Decisions Made This Phase
- Render derives every decision hash from disk through one shared matcher (D125), rather than trusting a hash staged in classified.json as the plan first said.
- Shortlist floor 2 / cap 10 chosen from measurements on the 2026-10-13 corpus (D124).
- The existing settled-page fetch test now uses a reject decision: a link whose commentary was never attached is no longer considered settled (step 5).
- Today's 25 uncommitted sync links were stashed from feature/leg-history-tiers (`stash@{0}`) before branching off main.
