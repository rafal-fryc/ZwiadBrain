# Phase 19 — Fix 3: grounding JS-rendered pages (deferred from PHASE-17)
Status: DONE

> Phase E continuation. PHASE-17 closed UA-gated + PDF fetch; the residual SB-53
> ground-drops are pages whose quotes are injected client-side (TechCrunch, some
> sd11.senate.ca.gov press releases) that a raw httpx GET cannot see.

## Goal
Let the deterministic grounding gate read text from JS-rendered pages so
verifier-confirmed quotes on client-rendered sources re-ground instead of
fail-closed dropping — while keeping the gate deterministic (NO LLM call).

## Design decision — RESOLVED (operator, 2026-06-07)
**Playwright, fail-closed.** Implemented as an OPTIONAL extra rather than a pure
out-of-pyproject probe: Playwright resolves clean (no typer<0.22 conflict, unlike
Docling/D68), so by the D73 "declare if it resolves clean" precedent it is declared in
`[project.optional-dependencies].render` — but kept out of the default deps (render-only,
needs a separate `playwright install chromium`). The render boundary still uses the
Docling-style lazy-import probe so absence is graceful. Logged as D78.

## What shipped
- `pipeline/playwright_render.py` — `playwright_available()` (top-level probe, swallows the
  `ModuleNotFoundError` that `find_spec` raises on an absent parent package) and
  `render_page_html(url)` (headless Chromium -> rendered DOM HTML; deterministic; never
  raises; `""` when absent/failed). Browser work isolated in `_render_with_playwright` so the
  never-raises wrapper is unit-testable without a real browser.
- `leg_history.reground_with_render(...)` — the two-pass retry (full list, original verdicts,
  renders ONLY quote-not-found urls). Returns `(result, js_recovered)`.
- CLI `render-leg-history` — runs the second pass only when `playwright_available()`; new
  `js-recovered` count in the summary line.
- `pyproject` optional `render` extra.

## Tasks
- [x] `pyproject` optional extra + `playwright_available()` probe + deterministic
      `render_page_html(url)` boundary (never raises; "" when absent/failed)
- [x] CLI two-pass retry (full list + original verdicts; renders only suspect urls);
      PHASE-18 dedup still applied over the result
- [x] Gate logic (`ground_items`/`ground_related`/`_normalize_text`/`_page_text`) BYTE-UNCHANGED
      — leg_history.py diff since the PHASE-18 commit is additive-only (65 insertions, 0 deletions)
- [x] Render summary reports a `js-recovered` count distinct from grounded/ground-drop
- [x] TDD: 6 `reground_with_render` unit + 4 boundary unit + 2 CLI integration
- [~] Live SB-53 re-render UAT — DEFERRED: Playwright + Chromium are not installed in this
      env (`playwright_available()` -> False), so a live render no-ops. Logic fully covered by
      the deterministic + integration tests. To run live: install the `render` extra +
      `playwright install chromium`, then re-render the SB-53 run dir.
- [x] Decision log entry (D78)

## Acceptance Criteria
- [x] A quote-not-found statement on a JS page re-grounds via the Playwright retry pass
- [x] Statements that grounded statically are not re-rendered (unit test asserts only the
      suspect url is passed to `render_html`)
- [x] Playwright absent => behaviour identical to PHASE-18 (no retry, no crash)
- [x] Gate logic byte-unchanged; 765 pytest, ruff clean, pyright baseline

## Gate / UAT note
- pytest: 753 -> 765 (+12). ruff: clean. pyright: 20 errors before and after — the same
  pre-existing baseline (third-party stubs in untouched files); my new/changed files are
  pyright-clean (`playwright_render.py` carries the same boundary pragma as `docling_text.py`).
- TDD finding: `importlib.util.find_spec("playwright.sync_api")` RAISES `ModuleNotFoundError`
  when the parent package is absent (it imports the parent to resolve the submodule) instead
  of returning None — the Docling probe only avoids this because Docling is installed. Fixed
  by probing the top-level package and swallowing the import error.

## Decisions Made This Phase
- **D78 (2026-06-07)** — Fix 3 is a two-pass CLI retry over the full list rendering only
  quote-not-found drops (no verdict remap); Playwright is an optional `render` extra; gate
  logic byte-unchanged. Full rationale in DECISIONS.md D78.
