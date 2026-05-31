# Phase 09 — Law-brain Commentary
Status: ACTIVE — design approved; implementation plan pending (writing-plans)

> Full design: docs/superpowers/specs/2026-05-29-phase09-lawbrain-commentary-design.md
> Locked decisions carried in: D2–D11, D14, D16. New decisions: D57–D63.
> Architecture: post-pivot slash-command/subagent model (D26/D27), mirrors
> /zwiad-scan-enforcement. Commentary-only — NO stub-minting (PHASE-11, discover=false).

## Goal
Attach the read-only sibling law brain (`Brains/law`) as a verbatim commentary
overlay onto items ZwiadBrain already tracks, via deterministic key-matching with an
LLM fallback gated by a deterministic shared-key grounding confirm.

## Tasks
(high-level; detailed task breakdown comes from the implementation plan)
- [ ] sources/lawbrain.py — read-only reader (enumerate, tolerant parse, content_hash D5, is_available)
- [ ] pipeline/lawbrain_keys.py — deterministic jurisdiction-qualified key extraction + tracked-item mapping + fail-closed
- [ ] pipeline/lawbrain_match.py — shortlist + confirm_match grounding (mirrors enforcement.py)
- [ ] pipeline/lawbrain_copy.py — build CommentarySource + idempotent merge + staleness
- [ ] pipeline/lawbrain_links.py — harvest [text](url) from page + referenced memos, denylist primary domains, dedup (D62)
- [ ] pipeline/lawbrain_registry.py — links.yaml load/query/record (D9 stickiness)
- [ ] models.py — CommentaryLink + CommentarySource.links (body-only); schema.py exclude links from frontmatter
- [ ] templates.py — _neutralize_wikilinks + ## Further Reading section + lawbrain:region markers + preserve_lawbrain_region (D63)
- [ ] cli.py — fetch-lawbrain-candidates + render-lawbrain-commentary (+ review resolution D61); render-refreshed/render-classified call preserve_lawbrain_region (D63)
- [ ] review-queue.md handling (pending/accept/reject; weak-grounding/collision/stale)
- [ ] .claude/agents/lawbrain-matcher.md — Read-only sonnet subagent
- [ ] .claude/commands/zwiad-sync-lawbrain.md — orchestration (+ --dry-run)
- [ ] zwiadbrain.toml [lawbrain] population (+ further_reading, primary_source_domains) + .env.example LAW_BRAIN_PATH
- [ ] tests (offline mini-wiki): reader, keys, match, copy, staleness, registry, review-queue, templates, links, further-reading, region-preservation
- [ ] DECISIONS D57–D63 + ARCHITECTURE + PLAN status; version bump v0.9.0

## Acceptance Criteria
- regulation-california-sb53-tfaia commentary attaches to ca-2025-sb-53 (deterministic key match)
- Re-run is byte-identical (D20, clean git status); commentary block carries markers + attribution + demoted headings + neutralized [[links]]
- LLM links pass deterministic shared-key confirm before auto-apply (D16); failures → review-queue, never silent
- Multi-subject slug-marker pages (tracker/landscape/map/scholarship) emit zero keys, attach nothing (D60)
- Cross-type matching works on shared key regardless of ZwiadBrain page kind (D59)
- ## Further Reading (via law brain) lists deduped law-firm/secondary links harvested from the matched page + its memos; primary .gov/legiscan links excluded (D62)
- Commentary + Further Reading survive /zwiad-refresh byte-identical (lawbrain:region preservation; not stripped) (D63)
- Brains/law is provably untouched (read-only, D2)
- ruff + pyright (strict) + pytest all green; v0.9.0; DECISIONS D57–D63 logged

## Decisions Made This Phase
(append as execution proceeds; D57–D61 specified in the design — log to DECISIONS.md during implementation)
