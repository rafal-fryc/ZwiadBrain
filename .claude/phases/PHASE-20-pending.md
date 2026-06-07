# Phase 20 — Grounding-fetch + Docling-converter caching (D76 deferred v2)
Status: PENDING

> Phase E continuation. D76 deferred two perf items: per-PDF DocumentConverter
> instantiation (heavyweight PyTorch construction every PDF) and re-fetching the
> same URL multiple times within one render run.

## Goal
Within a single render-leg-history run, fetch each distinct URL at most once and
reuse one Docling DocumentConverter across PDFs — no behavior change, just fewer
fetches/instantiations. Pure refactor (separate from any feature phase).

## Tasks
- [ ] Per-run fetch memo keyed by URL wrapping `gate_fetch` (statements + media share it)
- [ ] Lazily-constructed, run-scoped DocumentConverter reused by `_extract_pdf_text`
- [ ] Behavior byte-identical: same grounded/dropped sets before vs after (golden test)
- [ ] TDD: same URL fetched once across both gates; converter built at most once per run
- [ ] Gate: full pytest + ruff + pyright green
- [ ] Decision log entry

## Acceptance Criteria
- Identical grounding output to pre-refactor (golden comparison on the SB-53 run dir)
- A repeated URL triggers exactly one underlying fetch; converter constructed <= once
- Full gate green

## Notes / Risks
- REFACTOR only — no grounding-logic change. Must not alter the kept/dropped sets.
- Run-scoped (not process-global) cache to avoid cross-bill staleness.
