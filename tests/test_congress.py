"""Tests for the Congress.gov v3 source: discovery, enrichment mapping, retry/errors.

All HTTP is mocked with respx against committed fixture JSON — no live calls.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zwiadbrain.exceptions import RateLimitError, SourceFetchError
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.render import render_page
from zwiadbrain.sources.congress import CONGRESS_API_BASE, CongressSource

_FIX = Path(__file__).parent / "fixtures" / "congress"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _source() -> CongressSource:
    return CongressSource(api_key="test-key", max_attempts=3, wait_initial=0.0)


def _route_bill(mock: respx.MockRouter) -> None:
    base = "/bill/118/hr/8818"
    mock.get(base).respond(json=_fixture("detail.json"))
    mock.get(f"{base}/actions").respond(json=_fixture("actions.json"))
    mock.get(f"{base}/amendments").respond(json=_fixture("amendments.json"))
    mock.get(f"{base}/text").respond(json=_fixture("text.json"))
    mock.get(f"{base}/summaries").respond(json=_fixture("summaries.json"))
    mock.get(f"{base}/relatedbills").respond(json=_fixture("relatedbills.json"))


# --- discovery ------------------------------------------------------------


def test_discover_returns_candidates_for_a_congress() -> None:
    """should list a congress's bills as candidates with native ids and update cursor"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118").respond(json=_fixture("list.json"))
        candidates = _source().discover(congress=118, limit=10)
    assert [c.native_id for c in candidates] == ["118/hr/8818", "118/s/2024"]
    assert candidates[0].jurisdiction == "US"
    assert candidates[0].update_date == "2024-12-21T03:27:05Z"
    assert candidates[0].title == "Artificial Intelligence Accountability Act"


def test_discover_respects_limit() -> None:
    """should return no more candidates than the requested limit"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118").respond(json=_fixture("list.json"))
        candidates = _source().discover(congress=118, limit=1)
    assert len(candidates) == 1


# --- enrichment mapping ---------------------------------------------------


def test_fetch_maps_core_metadata_to_bill() -> None:
    """should map detail fields onto a Bill: id, number, chamber, sponsors, cursor"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert isinstance(bill, Bill)
    assert bill.id == "118-hr-8818"
    assert bill.jurisdiction == "US"
    assert bill.bill_number == "H.R. 8818"
    assert bill.chamber == "House"
    assert bill.congress == "118"
    assert bill.introduced_date == dt.date(2024, 6, 26)
    assert bill.policy_area == "Science, Technology, Communications"
    assert bill.sponsors == ["Rep. Lieu, Ted [D-CA-36]"]
    assert bill.update_date == "2024-12-21T03:27:05Z"
    assert bill.sources == {
        "Congress.gov": "https://www.congress.gov/bill/118th-congress/house-bill/8818"
    }


def test_fetch_builds_chronological_timeline() -> None:
    """should map actions oldest-first, including same-date actions in order"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert len(bill.actions) == 6
    assert bill.actions[0].date == dt.date(2024, 6, 26)
    assert bill.actions[0].text == "Introduced in House."
    # same-date action that occurred after introduction sorts immediately after it
    assert bill.actions[1].text == "Referred to the Committee on the Judiciary."
    assert bill.actions[-1].date == dt.date(2024, 12, 20)


def test_fetch_maps_amendments_with_chamber_and_explanation() -> None:
    """should map amendments with formatted number, chamber, status, and what_changed"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert len(bill.amendments) == 2
    house = next(a for a in bill.amendments if a.number == "H.Amdt. 512")
    assert house.chamber == "House"
    assert "transparency" in (house.what_changed or "")
    assert "agreed to" in (house.status or "")


def test_fetch_captures_text_versions_and_related_bills() -> None:
    """should map text versions (preferring formatted text) and related bills"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert [v.code for v in bill.text_versions] == [
        "Enrolled Bill",
        "Engrossed in House",
        "Introduced in House",
    ]
    assert bill.text_versions[0].url is not None
    assert bill.text_versions[0].url.endswith(".htm")
    assert bill.related_bills == ["S. 2024 (118th)"]


def test_fetch_detects_enactment_and_public_law() -> None:
    """should flag enacted bills and extract the public law number"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert bill.enacted is True
    assert bill.public_law == "118-265"
    assert bill.latest_action == "Became Public Law No: 118-265."
    assert bill.latest_action_date == dt.date(2024, 12, 20)


def test_fetch_detects_enactment_from_latest_action_without_laws_array() -> None:
    """should infer enactment + public law from latestAction text when laws[] is absent"""
    detail = _fixture("detail.json")
    detail["bill"].pop("laws")  # force the regex fallback rather than the laws[] path
    detail["bill"]["latestAction"] = {
        "actionDate": "2024-12-20",
        "text": "Became Public Law No: 118-300.",
    }
    base = "/bill/118/hr/8818"
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get(base).respond(json=detail)
        mock.get(f"{base}/actions").respond(json=_fixture("actions.json"))
        mock.get(f"{base}/amendments").respond(json=_fixture("amendments.json"))
        mock.get(f"{base}/text").respond(json=_fixture("text.json"))
        mock.get(f"{base}/summaries").respond(json=_fixture("summaries.json"))
        mock.get(f"{base}/relatedbills").respond(json=_fixture("relatedbills.json"))
        bill = _source().fetch("118/hr/8818")
    assert bill.enacted is True
    assert bill.public_law == "118-300"


def test_fetch_summary_is_official_text_with_html_stripped() -> None:
    """should populate summary from the latest official summary, stripped of HTML"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    assert bill.summary is not None
    assert "<" not in bill.summary
    assert bill.summary.startswith("Artificial Intelligence Accountability Act")
    assert "impact assessments" in bill.summary  # the latest (Public Law) summary, not the first


def test_fetched_bill_renders_a_page_with_timeline_and_amendments() -> None:
    """should render an enriched Bill to a page containing the standard sections"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        _route_bill(mock)
        bill = _source().fetch("118/hr/8818")
    page = render_page(bill)
    assert "## Summary" in page
    assert "## Status & Timeline" in page
    assert "## Amendments" in page
    assert "Introduced in House." in page


# --- transport: retry and error mapping -----------------------------------


def test_discover_retries_on_transient_server_error() -> None:
    """should retry a 5xx response and succeed on the following attempt"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        route = mock.get("/bill/118")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=_fixture("list.json")),
        ]
        candidates = _source().discover(congress=118, limit=10)
    assert route.call_count == 2
    assert len(candidates) == 2


def test_discover_raises_rate_limit_error_on_429() -> None:
    """should surface a 429 as a RateLimitError"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118").respond(429)
        with pytest.raises(RateLimitError):
            _source().discover(congress=118)


def test_fetch_raises_source_fetch_error_on_not_found() -> None:
    """should surface a 404 as a SourceFetchError"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/9999").respond(404)
        with pytest.raises(SourceFetchError):
            _source().fetch("118/hr/9999")


def test_discover_retries_on_transport_error_then_succeeds() -> None:
    """should retry a network (transport) error and succeed on the next attempt"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        route = mock.get("/bill/118")
        route.side_effect = [
            httpx.ConnectError("connection reset"),
            httpx.Response(200, json=_fixture("list.json")),
        ]
        candidates = _source().discover(congress=118, limit=10)
    assert route.call_count == 2
    assert len(candidates) == 2


def test_discover_raises_source_fetch_error_after_retry_exhaustion() -> None:
    """should give up after max_attempts of 5xx and surface a SourceFetchError"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        route = mock.get("/bill/118").respond(503)
        with pytest.raises(SourceFetchError):
            _source().discover(congress=118)
    assert route.call_count == 3  # max_attempts passed to _source()


def test_discover_since_window_uses_the_bill_endpoint() -> None:
    """should query /bill with a fromDateTime when given a since-window and no congress"""
    since = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        route = mock.get("/bill").respond(json=_fixture("list.json"))
        candidates = _source().discover(since=since, limit=10)
    assert route.called
    assert len(candidates) == 2
    assert "fromDateTime" in str(route.calls.last.request.url)
