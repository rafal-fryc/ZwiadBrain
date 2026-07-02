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
from zwiadbrain.models import Bill, CommitteeReport
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


def test_change_hashes_maps_bill_id_to_hash_skipping_non_bill_entries() -> None:
    """should return {bill_id: change_hash}, skipping the masterlist 'session' sub-object"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterListRaw": _fixture("getMasterListRaw.json")})
        hashes = _source().change_hashes()
    assert hashes == {1789012: "abc123-NEW", 1789055: "def456"}


# --- leg-history extraction (PHASE-16 / D75) --------------------------------


def test_fetch_leg_history_parses_votes() -> None:
    """should map getBill votes to a Vote list with date, chamber, result, and roll-call url"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill_leghistory.json")})
        inputs = _source().fetch_leg_history("1789012")
    assert [v.chamber for v in inputs.votes] == ["S", "A"]
    assert inputs.votes[0].date == dt.date(2023, 5, 31)
    assert inputs.votes[0].result == "Senate Third Reading — Passed 30-8"
    # state_link present on vote 0 wins; vote 1 has empty state_link so falls back to url.
    assert inputs.votes[0].roll_call_url == (
        "https://leginfo.legislature.ca.gov/faces/billVotesClient.xhtml?bill_id=202320240SB362"
    )
    assert inputs.votes[1].roll_call_url == "https://legiscan.com/CA/rollcall/SB362/id/555002"


def test_fetch_leg_history_maps_supplements_to_tier2_media() -> None:
    """should map url-bearing NON-analysis supplements to Tier-2 leads, skipping url-less ones

    PHASE-21: 'Analysis' supplements are promoted to spine committee_reports, so the only
    Tier-2 lead from this fixture is the fiscal note (the analysis moved out; the third
    supplement is link-less and skipped).
    """
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill_leghistory.json")})
        inputs = _source().fetch_leg_history("1789012")
    assert [m.kind for m in inputs.supplement_media] == ["page"]
    assert inputs.supplement_media[0].title == "Senate Appropriations Fiscal Note"
    assert inputs.supplement_media[0].note == "Fiscal Note"
    assert inputs.supplement_media[0].relation == "related"
    assert all(m.url for m in inputs.supplement_media)
    # The analysis is no longer a Tier-2 reference link.
    assert all("Analysis" not in m.title for m in inputs.supplement_media)


def test_fetch_leg_history_promotes_analyses_to_committee_reports() -> None:
    """PHASE-21: a 'Analysis' supplement becomes a spine CommitteeReport, not a Tier-2 lead"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill_leghistory.json")})
        inputs = _source().fetch_leg_history("1789012")

    assert [r.citation for r in inputs.committee_analyses] == ["Assembly Floor Analysis"]
    report = inputs.committee_analyses[0]
    assert isinstance(report, CommitteeReport)
    # state_link is empty on this supplement, so it falls back to the LegiScan mirror url.
    assert report.url == "https://legiscan.com/CA/supplement/SB362/id/88002"


def test_committee_analyses_exclude_fiscal_notes_and_misc() -> None:
    """only type=Analysis supplements are promoted; fiscal notes / misc stay out"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill_leghistory.json")})
        inputs = _source().fetch_leg_history("1789012")

    titles = [r.citation for r in inputs.committee_analyses]
    assert "Senate Appropriations Fiscal Note" not in titles  # fiscal note
    assert "Link-less supplement" not in titles  # misc, and url-less anyway


def test_fetch_leg_history_returns_enacted_bill() -> None:
    """should return the mapped enacted Bill alongside its votes and supplements"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill_leghistory.json")})
        inputs = _source().fetch_leg_history("1789012")
    assert inputs.bill.id == "ca-2023-sb-362"
    assert inputs.bill.enacted is True


def test_fetch_leg_history_uses_single_getbill_call() -> None:
    """should fetch the bill, votes, and supplements from exactly one getBill request"""
    payload = _fixture("getBill_leghistory.json")
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url=LEGISCAN_API_BASE).respond(200, json=payload)
        _source().fetch_leg_history("1789012")
    assert route.call_count == 1


# --- Session dataclass + list_sessions (PHASE-24) ---------------------------


def test_list_sessions_maps_getsessionlist_to_sessions() -> None:
    """should map getSessionList entries to Session records for the state"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSessionList": _fixture("getSessionList.json")})
        sessions = _source().list_sessions()
    assert [s.session_id for s in sessions] == [2016, 1791, 1624]
    assert sessions[-1].year_start == 2019
    assert sessions[-1].year_end == 2020
    assert sessions[-1].special is False
    assert sessions[-1].session_name == "2019-2020 Session"


# --- list_session_enacted (PHASE-24) ----------------------------------------


def test_list_session_enacted_keeps_only_passed_bills() -> None:
    """should keep status==4 rows, carry title+description, skip the session member"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": _fixture("getMasterList.json")})
        cands = _source().list_session_enacted(1624)
    assert [c.native_id for c in cands] == ["1132030", "1132099"]
    ab1 = cands[0]
    assert ab1.jurisdiction == "US-CA"
    assert "artificial intelligence" in (ab1.title.lower() + " " + (ab1.summary or "").lower())
    assert ab1.summary is not None
    assert ab1.raw.get("change_hash") == "hashA"


def test_list_session_enacted_respects_limit() -> None:
    """should cap the returned enacted candidates at limit"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": _fixture("getMasterList.json")})
        cands = _source().list_session_enacted(1624, limit=1)
    assert [c.native_id for c in cands] == ["1132030"]


def test_list_sessions_returns_empty_when_no_sessions() -> None:
    """should return [] when getSessionList omits the sessions key"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSessionList": {"status": "OK"}})
        assert _source().list_sessions() == []


def test_list_session_enacted_returns_empty_when_none_passed() -> None:
    """should return [] when no bill in the masterlist has status==4"""
    payload = {
        "status": "OK",
        "masterlist": {
            "session": {"session_id": 1624},
            "0": {
                "bill_id": 1,
                "number": "AB9",
                "change_hash": "h",
                "status": 6,
                "title": "x",
                "description": "y",
            },
        },
    }
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": payload})
        assert _source().list_session_enacted(1624) == []


def test_list_session_enacted_drops_memorializing_resolutions() -> None:
    """should drop K/J resolution rows, keep A/S bills, carry number onto raw (D92)"""
    payload = {
        "status": "OK",
        "masterlist": {
            "session": {"session_id": 1624},
            "0": {"bill_id": 10, "number": "A1746", "change_hash": "ha",
                  "status": 4, "title": "AI study", "description": "d"},
            "1": {"bill_id": 11, "number": "S3971", "change_hash": "hs",
                  "status": 4, "title": "AI study", "description": "d"},
            "2": {"bill_id": 12, "number": "K724", "change_hash": "hk",
                  "status": 4, "title": "Data Privacy Day", "description": "memorial"},
            "3": {"bill_id": 13, "number": "J512", "change_hash": "hj",
                  "status": 4, "title": "memorial", "description": "memorial"},
        },
    }
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": payload})
        cands = _source(state="ny").list_session_enacted(1624)
    assert [c.native_id for c in cands] == ["10", "11"]
    assert cands[0].raw.get("number") == "A1746"


# --- vote sanitization, dedup, and date/chamber guards (D111) -----------------


def _vote(
    *,
    date: str = "2023-05-31",
    chamber: str = "S",
    desc: str = "Senate Third Reading",
    passed: int = 1,
    yea: int = 30,
    nay: int = 8,
    state_link: str | None = None,
    url: str | None = None,
) -> dict[str, object]:
    return {
        "date": date,
        "chamber": chamber,
        "desc": desc,
        "passed": passed,
        "yea": yea,
        "nay": nay,
        "state_link": state_link,
        "url": url,
    }


def test_vote_result_strips_html_fragments_from_desc() -> None:
    """should strip HTML tags and attribute residue from a corrupted roll-call desc"""
    from zwiadbrain.sources.legiscan import _vote_result  # pyright: ignore[reportPrivateUsage]

    corrupted = _vote(desc='Assembly 3rd Reading AB1146lass="statusCell"> By Berman')
    assert _vote_result(corrupted) == "Assembly 3rd Reading AB1146 By Berman — Passed 30-8"


def test_parse_votes_dedups_identical_urlless_rows() -> None:
    """should keep exactly one row for repeated votes sharing date, chamber, and result"""
    from zwiadbrain.sources.legiscan import _parse_votes  # pyright: ignore[reportPrivateUsage]

    detail = {"votes": [_vote(), _vote(), _vote(), _vote(date="2023-06-02", chamber="A")]}
    votes = _parse_votes(detail, state="CA")
    assert len(votes) == 2
    assert votes[0].date == dt.date(2023, 5, 31)
    assert votes[1].date == dt.date(2023, 6, 2)


def test_parse_votes_dedups_by_roll_call_url() -> None:
    """should keep the first row when two votes share a roll-call url"""
    from zwiadbrain.sources.legiscan import _parse_votes  # pyright: ignore[reportPrivateUsage]

    detail = {
        "votes": [
            _vote(state_link="https://state.gov/vote/1"),
            _vote(desc="Different desc", state_link="https://state.gov/vote/1"),
        ]
    }
    votes = _parse_votes(detail, state="CA")
    assert len(votes) == 1
    assert votes[0].result == "Senate Third Reading — Passed 30-8"


def test_parse_votes_collapses_one_day_offset_phantom_pair() -> None:
    """should collapse two identical votes dated one day apart, keeping the later date

    Encodes the CA SB 53 audit case: a phantom 2025-09-12 Senate concurrence row next to
    the real 2025-09-13 vote (official record shows exactly one vote, on the 13th).
    """
    from zwiadbrain.sources.legiscan import _parse_votes  # pyright: ignore[reportPrivateUsage]

    detail = {
        "votes": [
            _vote(date="2025-09-12", desc="Senate Concurrence", yea=29, nay=8),
            _vote(date="2025-09-13", desc="Senate Concurrence", yea=29, nay=8),
        ]
    }
    votes = _parse_votes(detail, state="CA")
    assert len(votes) == 1
    assert votes[0].date == dt.date(2025, 9, 13)


def test_parse_votes_offset_pair_prefers_row_with_roll_call_url() -> None:
    """should keep the url-bearing row of a one-day phantom pair even when it is earlier"""
    from zwiadbrain.sources.legiscan import _parse_votes  # pyright: ignore[reportPrivateUsage]

    detail = {
        "votes": [
            _vote(date="2022-08-29", desc="Assembly 3rd Reading", yea=33, nay=0,
                  state_link="https://leginfo.legislature.ca.gov/vote/1"),
            _vote(date="2022-08-30", desc="Assembly 3rd Reading", yea=33, nay=0),
        ]
    }
    votes = _parse_votes(detail, state="CA")
    assert len(votes) == 1
    assert votes[0].roll_call_url == "https://leginfo.legislature.ca.gov/vote/1"


def test_parse_votes_keeps_genuinely_distinct_votes() -> None:
    """should never collapse votes that differ in result or are more than a day apart"""
    from zwiadbrain.sources.legiscan import _parse_votes  # pyright: ignore[reportPrivateUsage]

    detail = {
        "votes": [
            _vote(date="2023-05-31", desc="Senate Third Reading"),
            _vote(date="2023-06-01", desc="Assembly Concurrence", chamber="A", yea=60, nay=2),
            _vote(date="2023-06-05", desc="Senate Third Reading"),
        ]
    }
    votes = _parse_votes(detail, state="CA")
    assert len(votes) == 3


def test_normalize_chamber_corrects_spelled_out_house_only() -> None:
    """should remap the word House to the state's lower chamber and leave letter codes alone"""
    from zwiadbrain.sources.legiscan import (
        _normalize_chamber,  # pyright: ignore[reportPrivateUsage]
    )

    assert _normalize_chamber("CA", "House") == "Assembly"
    assert _normalize_chamber("VA", "House") == "House of Delegates"
    assert _normalize_chamber("TX", "House") == "House"
    assert _normalize_chamber("CA", "H") == "H"  # letter codes are jurisdiction-neutral
    assert _normalize_chamber("CA", "Senate") == "Senate"
    assert _normalize_chamber("CA", None) is None


def test_parse_date_treats_epoch_placeholder_as_none() -> None:
    """should return None for the 1969-12-31 epoch placeholder and keep real dates"""
    from zwiadbrain.sources.legiscan import _parse_date  # pyright: ignore[reportPrivateUsage]

    assert _parse_date("1969-12-31") is None
    assert _parse_date("0000-00-00") is None
    assert _parse_date("2026-01-05") == dt.date(2026, 1, 5)
