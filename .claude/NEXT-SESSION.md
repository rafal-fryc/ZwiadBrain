# ZwiadBrain — next-session handoff

> Written 2026-05-31 at the end of the PHASE-09 build. When you say "continue",
> start here. PHASE-09 (law-brain commentary overlay) is implemented and on
> `feature/phase-09-lawbrain-commentary` → **PR #4** (v0.9.0, 609 tests green,
> pyright/ruff clean). These are the OPERATOR / decision items that remain.

## A. Interactive UAT of `/zwiad-sync-lawbrain` (do this before/after merging PR #4)

The pipeline is built + unit-tested, but it has NOT yet been run against the real
law brain to actually attach commentary. Validate end-to-end:

1. Ensure the law brain is reachable: `LAW_BRAIN_PATH` env points to
   `C:/Users/rafst/Documents/projectas/Brains/law` (or the `[lawbrain] path` in
   `zwiadbrain.toml` does). `[lawbrain] enabled = true` already.
2. Run the slash command **`/zwiad-sync-lawbrain --dry-run`** first to preview the
   intended writes (no edits), then `/zwiad-sync-lawbrain` to apply.
   - (Or drive the halves directly: `uv run zwiadbrain fetch-lawbrain-candidates`
     → inspect `data/runs/<id>/lawbrain-candidates.json` → render.)
3. **Expected showcase:** `regulation-california-sb53-tfaia` deterministically
   matches tracked `ca-2025-sb-53` (key `US-CA::bill::SB-53`). Open
   `wiki/states/ca/bills/ca-2025-sb-53.md` and verify:
   - a `## Commentary & Analysis` block (verbatim body, `##`→`###` demoted,
     `[[wiki-slug]]` links flattened to plain text);
   - a `## Further Reading (via law brain)` section listing law-firm / IAPP /
     natlawreview links harvested from the page + its `sources/zwiad` memos, with
     `*.gov`/legiscan/wikipedia links excluded;
   - both wrapped in `<!-- lawbrain:region:begin/end -->` markers.
4. **Re-run is byte-identical** (clean `git status`); any weak/uncertain matches
   land in `wiki/review-queue.md`; decisions recorded in `wiki/links.yaml`.
5. **Confirm the law brain is untouched** (`Brains/law` — read-only, D2).
6. Review the rendered page(s), then commit them (review-before-commit, D26 —
   the command never auto-commits).

## B. Decisions / backlog (no code yet — just decide)

- **B1. Hardcoded path in `zwiadbrain.toml`** — `[lawbrain] path` is a
  machine-specific absolute path from the PHASE-01 scaffold. It works on this
  machine but is a portability smell. Decide: leave it, OR blank/remove it and
  rely on `LAW_BRAIN_PATH` in `.env` (then it's clean for any clone). Same applies
  to the example value in `.env.example`.
- **B2. State AGs** (carryover from PHASE-08) — all 7 priority-state AGs ship
  `enabled = false`; each needs its `item_selector` tuned against its live site
  before flipping `enabled = true` (CA OAG also needs a working feed URL).
- **B3. Gated future phases** — PHASE-10 (in-session scheduling) and PHASE-11
  (law-brain DISCOVERY / stub-minting, `discover=false`, D14) remain unbuilt.
  PHASE-11 should only be built if production shows official discovery regularly
  misses law-brain-known items; it may never be needed.

## Also
- **Merge PR #4** (squash per D19; optionally tag `v0.9.0` on the merge commit),
  then `git checkout main && git pull`.
- Delete this file once A + B are addressed.
