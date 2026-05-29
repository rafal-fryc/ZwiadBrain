"""Tests for the LegiScan source: transport, error/quota handling, redaction, mapping.

All HTTP is mocked with respx against committed fixture JSON — no live calls. Requests
are routed by the `op` query parameter via a side_effect handler.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zwiadbrain.exceptions import ConfigError, RateLimitError, SourceFetchError
from zwiadbrain.models import Bill
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


def test_fetch_maps_getbill_to_state_bill() -> None:
    """should map a getBill payload onto a Bill with the D48 id and US-CA jurisdiction"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert isinstance(bill, Bill)
    assert bill.id == "ca-2023-sb-362"
    assert bill.jurisdiction == "US-CA"
    assert bill.legiscan_bill_id == 1789012
    assert bill.bill_number == "SB 362"
    assert bill.session == "2023-2024 Regular Session"
    assert bill.congress is None
    assert bill.change_hash == "abc123def4567890abc123def4567890"
    assert bill.sources["LegiScan"] == "https://legiscan.com/CA/bill/SB362/2023"


def test_fetch_marks_chaptered_bill_enacted() -> None:
    """should treat status==4 / a Chaptered progress event as enacted"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert bill.enacted is True


def test_fetch_maps_sponsors_primary_first_and_timeline() -> None:
    """should order sponsors primary-first and map history into a dated timeline"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert bill.sponsors[0] == "Josh Becker"
    assert bill.introduced_date == dt.date(2023, 2, 8)
    assert bill.actions[0].date == dt.date(2023, 2, 8)
    assert bill.actions[-1].text.startswith("Chaptered")
    assert [t.code for t in bill.text_versions] == ["Introduced", "Chaptered"]
    assert bill.related_bills == ["Same As: AB1194"]


def test_fetch_maps_amendment_with_placeholder_date_to_none() -> None:
    """should map an adopted amendment and treat the 0000-00-00 placeholder date as None"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert bill.amendments[0].number == "Senate Amendment 1"
    assert bill.amendments[0].status == "adopted"
    assert bill.amendments[0].latest_action_date is None


def test_state_bill_renders_to_states_path_and_roundtrips() -> None:
    """should render a state bill under states/ca/bills and re-render byte-identically"""
    from zwiadbrain.pipeline.render import page_path, render_page
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    expected_suffix = "wiki/states/ca/bills/ca-2023-sb-362.md"
    assert page_path(bill, Path("wiki")).as_posix().endswith(expected_suffix)
    assert render_page(bill) == render_page(bill)


def test_discover_maps_search_results_to_candidates() -> None:
    """should yield relevance-ordered bill_id candidates with US-CA jurisdiction"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSearchRaw": _fixture("getSearchRaw.json")})
        cands = _source(query="privacy").discover(limit=10)
    assert [c.native_id for c in cands] == ["1789012", "1789055", "1789099"]
    assert cands[0].jurisdiction == "US-CA"
    assert cands[0].source == "legiscan"
    assert cands[0].title == ""  # getSearchRaw returns no titles
    assert cands[0].raw["change_hash"] == "abc123"


def test_discover_respects_limit() -> None:
    """should return no more than `limit` candidates"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSearchRaw": _fixture("getSearchRaw.json")})
        cands = _source(query="privacy").discover(limit=2)
    assert len(cands) == 2


def test_discover_without_query_raises() -> None:
    """should raise ConfigError when discover is called with no search query bound"""
    with pytest.raises(ConfigError):
        _source(query=None).discover(limit=5)
