# Phase 20 — Grounding-fetch + Docling-converter caching (D76 deferred v2)
Status: DONE

> Phase E continuation. D76 deferred two perf items: per-PDF DocumentConverter
> instantiation (heavyweight construction every PDF) and re-fetching the same URL
> multiple times within one render run (made concrete by PHASE-19's two-pass).

## Goal
Within a single render-leg-history run, fetch each distinct URL at most once and
reuse one Docling DocumentConverter across PDFs — no behavior change. Pure refactor
(separate from any feature phase).

## Tasks
- [x] Per-run fetch memo (`transcripts.memoize_fetch`) wrapping `make_gate_fetch(_fetch_url)`;
      shared by statement / hearing / media gates AND the PHASE-19 retry's static re-fetches
- [x] Lazily-constructed, cached `DocumentConverter` in `docling_text` (`_get_converter`)
      reused by `_extract_pdf_text` -> `extract_markdown`
- [x] Behavior byte-identical: full suite incl. render goldens passes unchanged; gate
      logic / `leg_history.py` untouched (empty git diff since the PHASE-19 commit)
- [x] TDD: 4 `memoize_fetch` unit (once-per-url / per-distinct-url / independent caches /
      caches error tuple) + 1 converter-reuse unit (built once across calls) + 1 CLI
      integration (shared url fetched once per render)
- [x] Gate: pytest 771 (+6), ruff clean, pyright at the unchanged 20-baseline
- [x] Decision log entry (D79)

## Acceptance Criteria
- [x] Identical grounding output to pre-refactor (full suite + render goldens unchanged)
- [x] A repeated URL triggers exactly one underlying fetch (CLI test asserts call count == 1);
      converter constructed <= once per run (unit test asserts instances == 1)
- [x] Full gate green

## Notes
- REFACTOR only — no grounding-logic change; `leg_history.py` diff since PHASE-19 is empty.
- Fetch memo is RUN-SCOPED (fresh per render) to avoid cross-bill staleness; the converter
  cache is process-level (a converter has no per-document state, so reuse is safe).
- TDD surfaced the cross-test isolation need for the module-level converter cache; the
  fake-docling installer now resets it (`monkeypatch.setattr(docling_text, "_converter", None)`).

## Decisions Made This Phase
- **D79 (2026-06-07)** — Per-run fetch memo + cached Docling converter; behavior-preserving,
  gate logic untouched. Full rationale in DECISIONS.md D79.
