"""Thin, typed boundary over Playwright's headless-Chromium page rendering (PHASE-19, Fix 3).

Playwright launches a real headless browser and downloads a Chromium build on first use,
so — like the Docling boundary (D68) — it is an optional, unlocked extra: this module is
the single deferred-import seam, the rest of the CLI stays cheap, and unit tests patch
this seam instead of touching a browser. Install it to enable JS-rendered grounding:

    uv pip install playwright
    uv run --no-sync playwright install chromium
"""

# Playwright is an optional, unlocked extra (it pulls a browser download) and is therefore
# absent from the type-check / CI environment, where pyright cannot resolve its types. This
# module is the single intentional boundary where that is tolerated; the rest of the codebase
# stays pyright-strict-clean.
# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import importlib.util

# Navigation budget for a single page render (ms). The gate is fail-closed, so a slow page
# that exceeds this simply yields "" and the item drops as if unfetchable.
_RENDER_TIMEOUT_MS = 30_000


def playwright_available() -> bool:
    """True when the Playwright python package can be imported in this environment.

    A successful import does NOT guarantee the Chromium browser binary is installed
    (``playwright install chromium``); a missing binary surfaces as a launch error that
    :func:`render_page_html` catches and turns into ``""`` (fail-closed).

    Probes the top-level ``playwright`` package: ``find_spec`` imports the parent to
    resolve a dotted submodule and would RAISE ``ModuleNotFoundError`` (not return None)
    when the package is absent, so the probe is top-level and the import error is swallowed.
    """
    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def render_page_html(url: str) -> str:
    """Return the post-JS DOM HTML of *url* via headless Chromium; ``""`` when unavailable.

    Deterministic (no LLM) and NEVER raises: the grounding gate must never crash a render,
    so an absent Playwright, a missing browser binary, a navigation timeout, or any other
    failure yields ``""`` and the caller fail-closed drops the item exactly as it would for
    an unfetchable page. The rendered HTML is processed by the gate's normal HTML text
    extraction, so a JS-injected quote is matched identically to a server-rendered one.
    """
    if not playwright_available():
        return ""
    try:
        return _render_with_playwright(url)
    except Exception:  # noqa: BLE001 — gate must never raise; any failure -> fail-closed ""
        return ""


def _render_with_playwright(url: str) -> str:
    """Launch headless Chromium, navigate to *url*, and return the rendered DOM HTML.

    Isolated from :func:`render_page_html` so the wrapper's never-raises contract can be
    unit-tested by patching this seam (no real browser in the test suite).
    """
    from playwright.sync_api import sync_playwright  # lazy: spawns a browser process

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=_RENDER_TIMEOUT_MS)
            html: str = page.content()
            return html
        finally:
            browser.close()
