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
    assert bill.update_date == "2024-12-21"
    assert bill.update_date_text == "2024-12-21T03:27:05Z"
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


def test_fetch_dedupes_duplicate_timeline_actions() -> None:
    """should collapse actions Congress repeats (same date + text) into one timeline row"""
    actions = {
        "actions": [
            {"actionDate": "2024-06-27", "text": "Referred to the Committee on the Judiciary."},
            {"actionDate": "2024-06-26", "text": "Introduced in House.", "type": "IntroReferral"},
            {"actionDate": "2024-06-26", "text": "Introduced in House.", "type": "Floor"},
        ]
    }
    base = "/bill/118/hr/8818"
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get(base).respond(json=_fixture("detail.json"))
        mock.get(f"{base}/actions").respond(json=actions)
        mock.get(f"{base}/amendments").respond(json=_fixture("amendments.json"))
        mock.get(f"{base}/text").respond(json=_fixture("text.json"))
        mock.get(f"{base}/summaries").respond(json=_fixture("summaries.json"))
        mock.get(f"{base}/relatedbills").respond(json=_fixture("relatedbills.json"))
        bill = _source().fetch("118/hr/8818")
    assert [(a.date, a.text) for a in bill.actions] == [
        (dt.date(2024, 6, 26), "Introduced in House."),
        (dt.date(2024, 6, 27), "Referred to the Committee on the Judiciary."),
    ]


def test_fetch_policy_area_returns_the_controlled_term() -> None:
    """should read a bill's policyArea name from a single core-detail request"""
    detail = {"bill": {"policyArea": {"name": "Science, Technology, Communications"}}}
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        route = mock.get("/bill/118/hr/8818").respond(json=detail)
        area = _source().fetch_policy_area("118/hr/8818")
    assert area == "Science, Technology, Communications"
    assert route.call_count == 1  # cheap probe: one request, no sub-resources


def test_fetch_policy_area_returns_none_when_absent() -> None:
    """should return None when the bill carries no policyArea"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/8818").respond(json={"bill": {}})
        assert _source().fetch_policy_area("118/hr/8818") is None


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


# --- recorded_votes ----------------------------------------------------------

# Congress.gov actions payload shape for recorded-vote tests.
# Each action may carry a ``recordedVotes`` list; the shape of each item is:
# {"rollNumber": str, "chamber": str, "congress": int, "date": str (ISO),
#  "sessionNumber": int, "url": str}
_ACTIONS_WITH_VOTES: dict[str, Any] = {
    "actions": [
        {
            "actionDate": "2024-12-20",
            "text": "Became Public Law No: 118-265.",
            "type": "BecameLaw",
        },
        {
            # House passage vote — has recordedVotes with its own date and URL
            "actionDate": "2024-12-18",
            "text": "On passage Passed by the Yeas and Nays: 350 - 80.",
            "type": "Floor",
            "recordedVotes": [
                {
                    "rollNumber": "521",
                    "chamber": "House",
                    "congress": 118,
                    "date": "2024-12-18T23:14:00Z",
                    "sessionNumber": 2,
                    "url": "https://clerk.house.gov/evs/2024/roll521.xml",
                }
            ],
        },
        {
            # Senate passage vote — recorded vote with a different date than actionDate
            "actionDate": "2024-09-10",
            "text": "Passed Senate by Yea-Nay Vote: 87 - 12.",
            "type": "Floor",
            "recordedVotes": [
                {
                    "rollNumber": "218",
                    "chamber": "Senate",
                    "congress": 118,
                    "date": "2024-09-10T18:44:00Z",
                    "sessionNumber": 2,
                    "url": "https://www.senate.gov/legislative/LIS/roll_call_lists/roll_call_vote_cfm.cfm?congress=118&session=2&vote=00218",
                }
            ],
        },
        {
            # Introduced — no recordedVotes key at all
            "actionDate": "2024-06-26",
            "text": "Introduced in House.",
            "type": "IntroReferral",
        },
    ],
    "pagination": {"count": 4},
}

# Payload where the recorded vote has no ``date`` field — should fall back to actionDate.
_ACTIONS_VOTE_NO_DATE: dict[str, Any] = {
    "actions": [
        {
            "actionDate": "2024-07-15",
            "text": "On motion to suspend the rules and pass Agreed to by voice vote.",
            "type": "Floor",
            "recordedVotes": [
                {
                    "rollNumber": "350",
                    "chamber": "House",
                    "congress": 118,
                    # no "date" field — must fall back to actionDate
                    "url": "https://clerk.house.gov/evs/2024/roll350.xml",
                }
            ],
        }
    ]
}


def test_recorded_votes_maps_recorded_vote_items_to_votes() -> None:
    """should return one Vote per recordedVotes item, with roll-call URL and chamber"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118/hr/8818/actions").respond(json=_ACTIONS_WITH_VOTES)
        votes = _source().recorded_votes("118/hr/8818")

    # Two actions carry recordedVotes; one action (Became Public Law) does not
    assert len(votes) == 2

    house_vote = votes[0]
    assert house_vote.chamber == "House"
    assert house_vote.date == dt.date(2024, 12, 18)
    assert house_vote.roll_call_url == "https://clerk.house.gov/evs/2024/roll521.xml"
    assert house_vote.result is None  # result is left None by design

    senate_vote = votes[1]
    assert senate_vote.chamber == "Senate"
    assert senate_vote.date == dt.date(2024, 9, 10)
    assert "senate.gov" in (senate_vote.roll_call_url or "")
    assert senate_vote.result is None


def test_recorded_votes_action_without_recorded_votes_contributes_nothing() -> None:
    """should skip an action that carries no recordedVotes while keeping one that does"""
    # Two actions: the first has no recordedVotes (must be skipped), the second has one.
    # The single resulting vote must be the one from the vote-carrying action — proving
    # the skip path is exercised, not just that a count happens to match.
    mixed_payload: dict[str, Any] = {
        "actions": [
            {
                "actionDate": "2024-06-26",
                "text": "Introduced in House.",
                "type": "IntroReferral",
                # no recordedVotes key → skipped
            },
            {
                "actionDate": "2024-12-18",
                "text": "On passage Passed by the Yeas and Nays: 350 - 80.",
                "type": "Floor",
                "recordedVotes": [
                    {
                        "rollNumber": "521",
                        "chamber": "House",
                        "congress": 118,
                        "date": "2024-12-18T23:14:00Z",
                        "url": "https://clerk.house.gov/evs/2024/roll521.xml",
                    }
                ],
            },
        ]
    }
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118/hr/8818/actions").respond(json=mixed_payload)
        votes = _source().recorded_votes("118/hr/8818")

    # Only the vote-carrying action contributes; the introduced action is skipped.
    assert len(votes) == 1
    assert votes[0].roll_call_url == "https://clerk.house.gov/evs/2024/roll521.xml"
    assert votes[0].date == dt.date(2024, 12, 18)


def test_recorded_votes_falls_back_to_action_date_when_rv_has_no_date() -> None:
    """should use actionDate as the vote date when the recordedVotes item has no date field"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118/hr/8818/actions").respond(json=_ACTIONS_VOTE_NO_DATE)
        votes = _source().recorded_votes("118/hr/8818")

    assert len(votes) == 1
    assert votes[0].date == dt.date(2024, 7, 15)
    assert votes[0].roll_call_url == "https://clerk.house.gov/evs/2024/roll350.xml"


def test_recorded_votes_returns_empty_list_when_no_actions_have_votes() -> None:
    """should return an empty list when no actions carry recordedVotes"""
    no_votes_payload: dict[str, Any] = {
        "actions": [
            {"actionDate": "2024-06-26", "text": "Introduced in House.", "type": "IntroReferral"},
            {"actionDate": "2024-07-15", "text": "Referred to committee.", "type": "IntroReferral"},
        ]
    }
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118/hr/8818/actions").respond(json=no_votes_payload)
        votes = _source().recorded_votes("118/hr/8818")

    assert votes == []


# --- T2: split cursors and amendment dates -----------------------------------


def test_fetch_maps_bare_update_date_and_update_date_text_separately() -> None:
    """should set update_date from bare updateDate, update_date_text from updateDateIncludingText"""
    detail_payload: dict[str, Any] = {
        "bill": {
            "congress": 118,
            "type": "HR",
            "number": 2670,
            "title": "Test bill",
            "updateDate": "2026-05-01T00:00:00Z",
            "updateDateIncludingText": "2026-05-02T00:00:00Z",
        }
    }
    empty_list_payloads: dict[str, dict[str, list[Any]]] = {
        "actions": {"actions": []},
        "amendments": {"amendments": []},
        "text": {"textVersions": []},
        "summaries": {"summaries": []},
        "relatedbills": {"relatedBills": []},
    }
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/2670").respond(json=detail_payload)
        for sub, body in empty_list_payloads.items():
            mock.get(f"/bill/118/hr/2670/{sub}").respond(json=body)
        bill = CongressSource(api_key="k").fetch("118/hr/2670")
    assert bill.update_date == "2026-05-01T00:00:00Z"
    assert bill.update_date_text == "2026-05-02T00:00:00Z"


def test_request_parses_retry_after_seconds_onto_retryable() -> None:
    """should read an integer Retry-After header on a 503 and carry it on the retry marker"""
    from zwiadbrain.sources.congress import (
        _retry_after_seconds,  # pyright: ignore[reportPrivateUsage]
        _Retryable,  # pyright: ignore[reportPrivateUsage]
    )

    resp = httpx.Response(503, headers={"Retry-After": "7"})
    assert _retry_after_seconds(resp) == 7.0
    # malformed / absent header → None (fall back to exponential)
    assert _retry_after_seconds(httpx.Response(503)) is None
    assert _retry_after_seconds(httpx.Response(503, headers={"Retry-After": "soon"})) is None
    # the marker carries the parsed value for the wait callable
    marker = _Retryable(503, "/bill/118", retry_after=7.0)
    assert marker.retry_after == 7.0


def test_discover_honors_retry_after_then_succeeds() -> None:
    """should retry a 503-with-Retry-After and succeed, using the header-driven wait"""
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        route = mock.get("/bill/118")
        route.side_effect = [
            httpx.Response(503, headers={"Retry-After": "0"}),
            httpx.Response(200, json=_fixture("list.json")),
        ]
        candidates = _source().discover(congress=118, limit=10)
    assert route.call_count == 2
    assert len(candidates) == 2


def test_fetch_maps_per_amendment_latest_action_date() -> None:
    """should map each amendment's latestAction.actionDate to Amendment.latest_action_date"""
    detail_payload: dict[str, Any] = {
        "bill": {"congress": 118, "type": "HR", "number": 2670, "title": "x"}
    }
    amendments_payload: dict[str, Any] = {
        "amendments": [
            {
                "type": "HAMDT",
                "number": "5",
                "purpose": "Adds AI clause",
                "latestAction": {"text": "Agreed to", "actionDate": "2026-04-15"},
            },
            {
                "type": "HAMDT",
                "number": "7",
                "purpose": "Strikes section 3",
                "latestAction": {"text": "Failed", "actionDate": "2026-04-20"},
            },
        ]
    }
    empty: dict[str, list[Any]] = {
        "actions": [], "textVersions": [], "summaries": [], "relatedBills": [],
    }
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/2670").respond(json=detail_payload)
        mock.get("/bill/118/hr/2670/actions").respond(json={"actions": empty["actions"]})
        mock.get("/bill/118/hr/2670/amendments").respond(json=amendments_payload)
        mock.get("/bill/118/hr/2670/text").respond(json={"textVersions": empty["textVersions"]})
        mock.get("/bill/118/hr/2670/summaries").respond(json={"summaries": empty["summaries"]})
        mock.get("/bill/118/hr/2670/relatedbills").respond(
            json={"relatedBills": empty["relatedBills"]}
        )
        bill = CongressSource(api_key="k").fetch("118/hr/2670")
    assert len(bill.amendments) == 2
    assert bill.amendments[0].latest_action_date == dt.date(2026, 4, 15)
    assert bill.amendments[1].latest_action_date == dt.date(2026, 4, 20)
