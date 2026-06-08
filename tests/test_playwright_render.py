"""Tests for the optional Playwright headless-render boundary (PHASE-19, Fix 3).

The real browser is never launched here: these tests patch the module seam, mirroring
how the Docling boundary is unit-tested. The live render is exercised only in UAT.
"""

import pytest

from zwiadbrain.pipeline import playwright_render
from zwiadbrain.pipeline.playwright_render import playwright_available, render_page_html


def test_playwright_available_returns_bool() -> None:
    """should report availability as a plain bool, never raise"""
    assert isinstance(playwright_available(), bool)


def test_render_returns_empty_when_playwright_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """should short-circuit to '' (no browser launch) when the package is unavailable"""
    monkeypatch.setattr(playwright_render, "playwright_available", lambda: False)
    assert render_page_html("https://example.test/x") == ""


def test_render_returns_empty_and_never_raises_on_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """should swallow any render failure (missing browser binary, timeout) into ''"""
    monkeypatch.setattr(playwright_render, "playwright_available", lambda: True)

    def _boom(url: str) -> str:
        raise RuntimeError("browser binary missing")

    monkeypatch.setattr(playwright_render, "_render_with_playwright", _boom)
    assert render_page_html("https://example.test/x") == ""


def test_render_returns_rendered_html_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """should return the rendered DOM HTML when the browser seam succeeds"""
    monkeypatch.setattr(playwright_render, "playwright_available", lambda: True)

    def _ok(url: str) -> str:
        return "<html><body>ok</body></html>"

    monkeypatch.setattr(playwright_render, "_render_with_playwright", _ok)
    assert render_page_html("https://example.test/x") == "<html><body>ok</body></html>"
