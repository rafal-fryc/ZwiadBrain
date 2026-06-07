# Phase 19 — Fix 3: grounding JS-rendered pages (deferred from PHASE-17)
Status: PENDING

> Phase E continuation. PHASE-17 closed UA-gated + PDF fetch; the residual SB-53
> ground-drops are pages whose quotes are injected client-side (TechCrunch, some
> sd11.senate.ca.gov press releases) that a raw httpx GET cannot see.

## Goal
Let the deterministic grounding gate read text from JS-rendered pages so
verifier-confirmed quotes on client-rendered sources re-ground instead of
fail-closed dropping — while keeping the gate deterministic (NO LLM call).

## Open design decision (confirm before building)
The gate is pure-Python httpx today. Rendering JS needs a headless browser. Options:
1. **`browse` skill daemon** (headless Chromium already installed for this repo) —
   shell out from `_fetch_url`'s render fallback; no new Python dep.
2. **Playwright Python dep** — in-process, but adds a heavyweight (~browser download)
   dependency to a library that otherwise stays light; conflicts to vet vs typer pin.
3. **Keep deferred** — accept JS pages as correct fail-closed drops; do nothing.
Decision must be logged (D-next) before implementation.

## Tasks (provisional — finalize after the decision)
- [ ] Render fallback in `_fetch_url`: HTTP first; on a 200 HTML whose quote-text is
      absent, escalate to a headless render (chosen mechanism); deterministic, never-raises
- [ ] Gate logic (`ground_items`/`ground_related`/`_normalize_text`/`_page_text`) byte-unchanged
- [ ] TDD: render path invoked only on fallback; absent-tool -> graceful ""; HTML regression
- [ ] Live SB-53 re-render UAT: yield rises from 9/18
- [ ] Decision log entry

## Acceptance Criteria
- A JS-rendered fixture grounds via the render fallback; static HTML path unchanged
- Gate stays deterministic and logic byte-unchanged (git diff)
- Full gate green
