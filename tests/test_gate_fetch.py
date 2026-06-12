"""Tests for the grounding-gate fetcher `_fetch_url` (PHASE-17 / D76).

Fix 1 — send a browser User-Agent so UA-gated hosts (e.g. gov.ca.gov) return 200.
Fix 2 — extract text from PDF responses via the Docling boundary so PDF-sourced
quotes can re-ground. The gate stays deterministic and `_fetch_url` never raises.
"""

import httpx
import pytest
import respx

from zwiadbrain.cli import _fetch_url  # pyright: ignore[reportPrivateUsage]
from zwiadbrain.exceptions import ExtractionError

_URL = "https://example.gov/doc"


def test_fetch_url_sends_browser_user_agent() -> None:
    """should send a browser-like User-Agent (not the default python-httpx UA)"""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).mock(side_effect=handler)
        status, _ = _fetch_url(_URL)
    assert status == 200
    # A real browser token is what defeats WAFs that 403 the default "python-httpx/x" UA.
    assert "Mozilla" in seen["ua"]
    assert "python-httpx" not in seen["ua"]


def test_fetch_url_defeats_ua_gated_403() -> None:
    """should get 200 from a host that 403s non-browser User-Agents (gov.ca.gov-style WAF)"""
    def handler(request: httpx.Request) -> httpx.Response:
        if "Mozilla" in request.headers.get("user-agent", ""):
            return httpx.Response(200, text="the quote is here")
        return httpx.Response(403, text="forbidden")

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).mock(side_effect=handler)
        status, body = _fetch_url(_URL)
    assert status == 200
    assert "the quote is here" in body


def test_fetch_url_extracts_pdf_via_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    """should extract text from a 200 PDF response via the Docling boundary"""
    def fake_extract(_src: object) -> str:
        return "## Analysis\n\nthe pdf quote text"

    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: True)
    monkeypatch.setattr("zwiadbrain.cli.extract_markdown", fake_extract)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(
            200, content=b"%PDF-1.5 binary bytes", headers={"content-type": "application/pdf"}
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert body == "## Analysis\n\nthe pdf quote text"


def test_fetch_url_pdf_detected_by_magic_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """should detect a PDF by its %PDF- magic bytes even when content-type is generic"""
    def fake_extract(_src: object) -> str:
        return "extracted body"

    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: True)
    monkeypatch.setattr("zwiadbrain.cli.extract_markdown", fake_extract)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(
            200, content=b"%PDF-1.7 ...", headers={"content-type": "application/octet-stream"}
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert body == "extracted body"


def test_fetch_url_pdf_without_docling_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """should fail closed (empty body) when a PDF is fetched but Docling is absent"""
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: False)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(
            200, content=b"%PDF-1.5 bytes", headers={"content-type": "application/pdf"}
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert body == ""


def test_fetch_url_pdf_extraction_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """should fail closed (empty body) when Docling extraction raises"""
    def boom(_src: object) -> str:
        raise ExtractionError("docling blew up")

    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: True)
    monkeypatch.setattr("zwiadbrain.cli.extract_markdown", boom)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(
            200, content=b"%PDF-1.5 bytes", headers={"content-type": "application/pdf"}
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert body == ""


def test_fetch_url_html_returns_body_unchanged() -> None:
    """should return the HTML body unchanged for a normal 200 text/html response"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(
            200, text="<p>hello world</p>", headers={"content-type": "text/html"}
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert body == "<p>hello world</p>"


def test_fetch_url_non_200_reports_status() -> None:
    """should report a non-200 status so the gate drops the item"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(404, text="nope")
        status, _ = _fetch_url(_URL)
    assert status == 404


def test_fetch_url_network_error_returns_zero() -> None:
    """should return (0, '') when both the live fetch and the Wayback fallback fail"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).mock(side_effect=httpx.ConnectError("boom"))
        mock.get(url=f"https://web.archive.org/web/2/{_URL}").respond(404, text="")
        assert _fetch_url(_URL) == (0, "")


def test_fetch_url_blocked_falls_back_to_wayback() -> None:
    """should ground via the Wayback snapshot when the live fetch is bot-blocked (D78d)"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(403, text="Just a moment...")
        mock.get(url=f"https://web.archive.org/web/2/{_URL}").respond(
            200, text="<p>the archived quote</p>"
        )
        status, body = _fetch_url(_URL)
    assert status == 200
    assert "the archived quote" in body


def test_fetch_url_wayback_failure_keeps_original_status() -> None:
    """should keep the live 403 when the Wayback snapshot also fails"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=_URL).respond(403, text="blocked")
        mock.get(url=f"https://web.archive.org/web/2/{_URL}").respond(404, text="")
        status, _ = _fetch_url(_URL)
    assert status == 403
