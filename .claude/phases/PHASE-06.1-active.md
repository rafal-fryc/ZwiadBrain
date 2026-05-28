# Phase 06.1 — Hardening (full-system review remediation)
Status: ACTIVE

> Full plan: `docs/superpowers/plans/2026-05-28-phase06.1-hardening.md` (56 TDD tasks).
> Source: the 2026-05-28 full-system review (10 dimensions, 85 findings: 3 HIGH, ~80 medium/low, 0 critical, 0 refuted).
> TDD throughout (test first, watch it fail, implement, watch it pass, commit). Atomic commits per task; refactor commits separate from fix commits.
> Branch: off `feature/phase-06-watchlist-refresh` (PHASE-06 not yet merged to main); merges alongside the PHASE-06 PR.

## Goal
Remediate the reviewed findings — tighten the leg-history trust boundary (F2), harden error isolation (F4/F5) and the SQLite/source boundaries, validate the domain models, fix documentation drift, and close follow-ups F1/F4/F5/F6/F7 — without changing the D20 (byte-identical render), D26 (interactive-only LLM), or D36 (fail-closed grounding) invariants.

## Tasks
- [ ] B1 — Docs & onboarding truth: new `ARCHITECTURE.md`; rewrite README; PLAN.md staleness banner + phase reconciliation; fix cli.py docstrings; delete dead `llm/` stub. (5 tasks)
- [ ] B2 — Decisions: log D41 (automation direction — RECOMMENDED hybrid, needs user confirm); D42 (classifier `haiku`→`sonnet`); DECISIONS notes for D36 recall, D33 pagination home, topics-retention-on-flip. (3 tasks)
- [ ] B3 — Prompts/trust boundary: verifier single-speaker contiguity check **(c)** [HIGH, F2]; researcher single-attribution rule; researcher normalization wording; verifier echo `quote_prefix`/`speaker` + CLI cross-check; classifier `criterion` field split; summarizer/explainer no-fabrication clause. (7 tasks)
- [ ] B4 — Models & shared id parser: new `pipeline/ids.py::parse_bill_id` (raises `ConfigError`) + `Bill.id` validator [F4 source]; bound `confidence` 0..1; `min_length` on quote/reason/citation; `http(s)` validators on URL fields; `update_date` type note; missing-discriminator test. (9 tasks)
- [ ] B5 — Pipeline & CLI robustness: `from_page` YAML wrap → `WikiSchemaError` [HIGH, F5 surface]; F1 cursor stamping in render-leg-history + render-refreshed; F6 `summary_hash` dedup; per-page isolation + `parse_bill_id` in fetch-refreshable [F4/F5]; render-classified malformed-input guard; staging-validation/run-dir helpers; F7 `--force` re-track; arg validation; key-order/report polish. (11 tasks)
- [ ] B6 — Sources & store robustness: honor `Retry-After` (503/429); `StoreError(AppError)` + corrupt-DB self-heal; `reindex` explicit transaction; FTS insert-or-replace; granuleId flatten; Source.discover protocol alignment; api-key redaction; int-cast/text-version guards; FTS query safety. (14 tasks)
- [ ] B7 — Render/D20 & grounding hygiene: drop `last_synced` from frontmatter [D20 footgun]; empty leg-history section guard; `_page_text` strip `script`/`style`/`noscript`; D20 parse→render→parse byte-identity test; merged-attribution gate-blindspot doc test; heading-demote h6 cap; exact drop-reason asserts. (7 tasks)
- [ ] B8 — Close-out: full gate green (ruff + pyright strict + pytest); version → 0.6.1; tag `v0.6.1`; interactive UAT (verifier rejects a merged-attribution quote; refresh idempotent after leg-history regen).

## Acceptance Criteria
- All 3 HIGH findings fixed: a real README + ARCHITECTURE.md exist; one malformed committed page no longer aborts `reindex` (per-page isolation); the verifier rejects a merged/cross-attribution quote.
- F1/F4/F5/F6 closed; F7 `--force` re-track implemented (explicit single-bill, pending D41 confirmation).
- D20 byte-identical invariant pinned by a parse→render→parse round-trip test; `last_synced` no longer churns frontmatter.
- Grounding gate strips non-visible nodes; `parse_bill_id` is the single id parser and raises `ConfigError`; `summary_hash` has one implementation.
- ruff + pyright (strict) + pytest all green; version 0.6.1 tagged.
- D41 + D42 logged; D34 leg_history split explicitly deferred to a separate gated plan.

## Decisions Made This Phase
- D41 — automation/cron story (RECOMMENDED: hybrid headless-detection + interactive-dispatch; **awaiting user confirmation** before PHASE-10; gates B23/B59).
- D42 — classifier model `haiku`→`sonnet` for precision-gate robustness (cost trade-off logged).
- Carve-out: D34 leg_history spine/research split is OUT of scope here — separate gated refactor plan, after this lands.
