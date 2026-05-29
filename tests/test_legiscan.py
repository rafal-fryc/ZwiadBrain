"""Tests for the LegiScan source: transport, error/quota handling, redaction, mapping.

All HTTP is mocked with respx against committed fixture JSON — no live calls. Requests
are routed by the `op` query parameter via a side_effect handler.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zwiadbrain.exceptions import RateLimitError, SourceFetchError
from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE, LegiScanSource

_FIX = Path(__file__).parent / "fixtures" / "legiscan"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _source(state: str = "ca", *, query: str | None = None) -> LegiScanSource:
    return LegiScanSource("test-key", state, query=query, max_attempts=3, wait_initial=0.0)


def _route_by_op(mock: respx.MockRouter, mapping: dict[str, dict[str, Any]]) -> None:
    """Route every GET to the base URL, returning the fixture for the request's `op`."""
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json=mapping[op])
    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


def test_error_status_with_quota_message_raises_rate_limit() -> None:
    """should raise RateLimitError when the body status is ERROR with a quota message"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("error_quota.json")})
        with pytest.raises(RateLimitError):
            _source().fetch("42")


def test_error_status_other_message_raises_fetch_error() -> None:
    """should raise SourceFetchError on a non-quota ERROR body"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("error_other.json")})
        with pytest.raises(SourceFetchError):
            _source().fetch("42")


def test_http_429_raises_rate_limit() -> None:
    """should raise RateLimitError on an HTTP 429"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).respond(status_code=429)
        with pytest.raises(RateLimitError):
            _source().fetch("42")


def test_http_500_retries_then_raises_fetch_error() -> None:
    """should retry a 5xx and surface SourceFetchError after attempts are exhausted"""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url=LEGISCAN_API_BASE).respond(status_code=503)
        with pytest.raises(SourceFetchError):
            _source().fetch("42")
        assert route.call_count == 3
