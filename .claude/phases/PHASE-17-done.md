# Phase 17 — Grounding-gate fetch hardening (Phase E, part 1)
Status: DONE

> Follows PHASE-16's live UAT, which surfaced the gate-vs-verifier fetch asymmetry.
> One active phase at a time. Approved by the operator: "reuse docling, do fix 1 and 2".

## Goal
Make the deterministic grounding-gate fetcher (`cli._fetch_url`) as capable as the verifier's WebFetch for the two common failure modes — send a browser **User-Agent** (Fix 1) and extract text from **PDF** responses via the existing Docling boundary (Fix 2) — so verifier-confirmed quotes on UA-gated or PDF sources re-ground instead of fail-closed dropping. The gate LOGIC (`ground_items`/`ground_related`/`_normalize_text`/`_page_text`) stays byte-unchanged; only the fetch layer changes. The gate stays deterministic — NO LLM call (preserves the cross-modal independence between gate and verifier).

## Tasks
- [x] Fix 1: `User-Agent` (+ `Accept`) header on `_fetch_url` via `_GATE_HEADERS` — TDD (browser-UA sent; UA-gated 403→200)
- [x] Fix 2: PDF detection (`_is_pdf_response`: content-type or `%PDF-` magic bytes); 200-PDF → `_extract_pdf_text` (temp file → Docling `extract_markdown`); deterministic, never-raises, `""` when Docling absent/extraction fails — TDD
- [x] Kept `ground_items`/`ground_related`/`_normalize_text`/`_page_text` BYTE-UNCHANGED — confirmed by `git diff` (leg_history.py has zero diff this phase; only `cli._fetch_url` changed)
- [x] Tests (TDD): browser-UA sent; UA-gate 403→200; 200 PDF + docling → extracted text; PDF magic-byte detection; PDF + docling absent → ""; PDF extraction-error → ""; HTML regression; non-200; never-raises on transport error — 9 tests, RED→GREEN
- [x] Gate: **744 pytest** (+9), ruff clean, pyright clean
- [x] Live re-render UAT: re-ran `render-leg-history` on the SB-53 run dir — see below
- [x] Decision log: D76 (DECISIONS.md)

## Acceptance Criteria
- `_fetch_url` sends a UA and extracts PDF text via the Docling boundary; gate logic unchanged (verified by diff)
- Full gate green (pytest + ruff + pyright)
- A re-render of SB-53 recovers the gov.ca.gov signing statement (Fix 1) and, with Docling installed, the PDF committee-analysis quotes (Fix 2); statement yield rises from the PHASE-16 baseline of 4/18

## Files to touch
- src/zwiadbrain/cli.py (`_fetch_url` + a PDF-extract helper; import `extract_markdown`)
- tests/test_gate_fetch.py (new) · DECISIONS.md

## Notes / Risks
- Gate must NEVER call an LLM — Docling text extraction is deterministic, so this is fine; do not route the gate through WebFetch/any model.
- Docling is optional/unlocked (D68); absent → PDF path returns "" (graceful fail-closed), so the type-check/CI env is unaffected and unit tests mock the boundary.
- Docling is heavyweight (PyTorch); per-PDF `DocumentConverter` instantiation is acceptable for an interactive render — converter caching deferred.
- Deferred still: Fix 3 (JS rendering via headless browser) and the single-shared-fetch-cache rearchitecture — open only on demonstrated need.

## Live re-render UAT result (2026-06-04 — ca-2025-sb-53, hardened gate)
Re-ran `render-leg-history` on the PHASE-16 SB-53 run dir through the hardened `_fetch_url` (Docling **is** installed in this env). Statement yield **4/18 → 9/18 grounded** (hearings 6/6, media 13/13, votes 12, narrative — unchanged):
- **Fix 1 (browser UA)** recovered **Governor Newsom's signing statement** — gov.ca.gov no longer 403s the gate. (It grounds twice: the press-lane "Gavin Newsom" + signing-lane "Gov. Gavin Newsom" near-dup that dedup-by-`(speaker,quote)` doesn't collapse — a future quote-only/speaker-normalized dedup could; noted, out of scope.)
- **Fix 2 (Docling PDF)** recovered 3 Wiener committee-analysis quotes from the APCP PDF that previously returned un-parseable bytes.
- **Residual 9 drops are correct fail-closed behavior, not defects:** JS-rendered pages (TechCrunch, and a few sd11.senate.ca.gov press pages whose quotes are injected client-side) → the deferred **Fix 3** (headless render); and pathological PDF formatting (the `10²⁶` superscript quote; two Newsom SB-1047 veto passages whose dashes/curly-quotes differ after extraction) → genuinely unmatchable verbatim.

Outcome: the gate-vs-verifier fetch asymmetry is closed for the two common modes (UA-gated hosts + PDFs) with the gate still fully deterministic and its logic byte-unchanged. Acceptance criteria 1–3 met.

## Decisions Made This Phase
- **D76 (2026-06-04)** — Grounding-gate fetcher hardened: browser `User-Agent` (Fix 1) + Docling PDF text extraction (Fix 2) in `cli._fetch_url`; deterministic, never-raises, gate logic byte-unchanged. Full rationale in DECISIONS.md D76.
