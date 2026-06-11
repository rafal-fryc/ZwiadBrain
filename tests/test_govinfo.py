"""Tests for the GovInfo API client: related, search, typed leg-history mappers, retry/errors.

All HTTP is mocked with respx against committed fixture JSON — no live calls.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zwiadbrain.exceptions import RateLimitError, SourceFetchError, SourceNotFoundError
from zwiadbrain.models import CommitteeReport, Enactment, FloorAction, Hearing
from zwiadbrain.sources.govinfo import (
    GOVINFO_API_BASE,
    GovInfoSource,
    _flatten_str,  # pyright: ignore[reportPrivateUsage]
    _parse_public_law,  # pyright: ignore[reportPrivateUsage]
    _retry_after_seconds,  # pyright: ignore[reportPrivateUsage]
    details_url,
    enrolled_bill_package_id,
)

_FIX = Path(__file__).parent / "fixtures" / "govinfo"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _source() -> GovInfoSource:
    return GovInfoSource(api_key="test-key", max_attempts=3, wait_initial=0.0)


# --- pure helpers -----------------------------------------------------------


def test_enrolled_bill_package_id_formats_correctly() -> None:
    """should produce BILLS-{congress}{type_lower}{number}enr"""
    assert enrolled_bill_package_id(118, "HR", 8818) == "BILLS-118hr8818enr"
    assert enrolled_bill_package_id(118, "S", 2024) == "BILLS-118s2024enr"
    assert enrolled_bill_package_id(117, "HJRES", 192) == "BILLS-117hjres192enr"


def test_details_url_without_granule_id() -> None:
    """should return the app/details base URL without a trailing segment"""
    assert details_url("PLAW-118publ42") == "https://www.govinfo.gov/app/details/PLAW-118publ42"


def test_details_url_with_granule_id() -> None:
    """should append the granuleId when provided"""
    assert details_url("CREC-2024-12-18", "CREC-2024-12-18-pt1-PgH8818") == (
        "https://www.govinfo.gov/app/details/CREC-2024-12-18/CREC-2024-12-18-pt1-PgH8818"
    )


def test_parse_public_law_extracts_congress_and_number() -> None:
    """should parse PLAW-118publ42 to '118-42'"""
    assert _parse_public_law("PLAW-118publ42") == "118-42"
    assert _parse_public_law("PLAW-117publ7") == "117-7"


def test_parse_public_law_returns_none_on_non_match() -> None:
    """should return None for package IDs that don't match the PLAW pattern"""
    assert _parse_public_law("CRPT-118hrpt712") is None
    assert _parse_public_law("") is None
    assert _parse_public_law("BILLS-118hr1234enr") is None
    # anchored: an embedded PLAW substring must not match
    assert _parse_public_law("PREFIX-PLAW-118publ42") is None
    # private law (pvtl) is not a public law
    assert _parse_public_law("PLAW-118pvtl5") is None


# --- related primitive ------------------------------------------------------


def test_related_returns_results_list() -> None:
    """should return the 'results' list from a /related endpoint"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/CRPT").respond(json=_fixture("related_crpt.json"))
        results = _source().related(pkg_id, "CRPT")
    assert len(results) == 1
    assert results[0]["packageId"] == "CRPT-118hrpt712"


def test_related_returns_empty_list_when_no_results() -> None:
    """should return an empty list when the API returns no results"""
    pkg_id = enrolled_bill_package_id(118, "HR", 9999)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(json=_fixture("related_empty.json"))
        results = _source().related(pkg_id, "PLAW")
    assert results == []


# --- package_summary --------------------------------------------------------


def test_package_summary_returns_summary_dict_for_package() -> None:
    """should GET /packages/{packageId}/summary and return the parsed metadata dict"""
    summary = {
        "packageId": "PLAW-118publ42",
        "title": "An Act to do something",
        "dateIssued": "2024-12-20",
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.get("/packages/PLAW-118publ42/summary").respond(json=summary)
        result = _source().package_summary("PLAW-118publ42")
    assert route.call_count == 1
    assert route.calls.last.request.url.path == "/packages/PLAW-118publ42/summary"
    assert result == summary


# --- committee_reports ------------------------------------------------------


def test_committee_reports_maps_crpt_results_to_committee_reports() -> None:
    """should map CRPT related results to CommitteeReport with app/details URLs"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/CRPT").respond(json=_fixture("related_crpt.json"))
        reports = _source().committee_reports(118, "HR", 8818)
    assert len(reports) == 1
    assert isinstance(reports[0], CommitteeReport)
    assert reports[0].citation == "H. Rept. 118-712 - ARTIFICIAL INTELLIGENCE ACCOUNTABILITY ACT"
    assert reports[0].url == "https://www.govinfo.gov/app/details/CRPT-118hrpt712"


def test_committee_reports_returns_empty_list_when_none() -> None:
    """should return an empty list when no committee reports exist"""
    pkg_id = enrolled_bill_package_id(118, "HR", 9999)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/CRPT").respond(json=_fixture("related_empty.json"))
        reports = _source().committee_reports(118, "HR", 9999)
    assert reports == []


# --- enacted_law ------------------------------------------------------------


def test_enacted_law_maps_plaw_to_enactment() -> None:
    """should map the first PLAW result to an Enactment with parsed public_law and url"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(json=_fixture("related_plaw.json"))
        mock.get("/related/PLAW-118publ42/STATUTE").respond(json=_fixture("related_statute_empty.json"))
        enactment = _source().enacted_law(118, "HR", 8818)
    assert isinstance(enactment, Enactment)
    assert enactment.public_law == "118-42"
    assert enactment.url == "https://www.govinfo.gov/app/details/PLAW-118publ42"
    # date_signed is not populated by this method; statutes_at_large is None (empty fixture)
    assert enactment.date_signed is None
    assert enactment.statutes_at_large is None


def test_enacted_law_returns_none_when_no_plaw_results() -> None:
    """should return None when there are no PLAW results for this bill"""
    pkg_id = enrolled_bill_package_id(118, "HR", 9999)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(json=_fixture("related_empty.json"))
        assert _source().enacted_law(118, "HR", 9999) is None


# --- hearings ---------------------------------------------------------------


def test_hearings_maps_chrg_search_results_to_hearings() -> None:
    """should POST the right query and map CHRG results to Hearing objects"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.post("/search").respond(json=_fixture("search_chrg.json"))
        hearings = _source().hearings(118, "H.R. 8818")
    assert route.call_count == 1
    # verify POST body carries correct query
    posted = json.loads(route.calls.last.request.content)
    assert 'collection:CHRG' in posted["query"]
    assert 'congress:118' in posted["query"]
    assert 'H.R. 8818' in posted["query"]

    assert len(hearings) == 2
    assert isinstance(hearings[0], Hearing)
    assert hearings[0].title == "Hearing on Artificial Intelligence Accountability"
    assert hearings[0].committee == "House Committee on the Judiciary"
    assert hearings[0].date == dt.date(2024, 3, 15)
    assert hearings[0].citation == "CHRG-118hhrg54321"
    # first result has no granuleId → app/details/{packageId}
    assert hearings[0].url == "https://www.govinfo.gov/app/details/CHRG-118hhrg54321"
    # second result has granuleId → app/details/{packageId}/{granuleId}
    assert hearings[1].url == (
        "https://www.govinfo.gov/app/details/CHRG-118shrg99001/CHRG-118shrg99001-gpo1"
    )


def test_hearings_tolerant_when_optional_fields_missing() -> None:
    """should not raise when granuleId and governmentAuthor are absent from search results"""
    minimal_result = {
        "count": 1,
        "results": [
            {
                "title": "Hearing on Something",
                "packageId": "CHRG-118hhrg00001",
                # granuleId absent entirely
                # governmentAuthor absent entirely
                "collectionCode": "CHRG",
                "dateIssued": "2024-01-01",
            }
        ],
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(json=minimal_result)
        hearings = _source().hearings(118, "H.R. 1")
    assert len(hearings) == 1
    assert hearings[0].committee is None
    assert hearings[0].url == "https://www.govinfo.gov/app/details/CHRG-118hhrg00001"


def test_hearings_flattens_list_governmentAuthor_to_most_specific_string() -> None:
    """live GovInfo /search returns governmentAuthor as a list — coerce to last non-empty string

    Regression for a UAT failure: a CHRG hit on 118/hr/2670 returned
    ``governmentAuthor: ["Congress", "House of Representatives"]``, and the
    previous code passed it straight to ``Hearing(committee=str|None)`` which
    Pydantic rejected with a string_type error.
    """
    list_author_result = {
        "count": 1,
        "results": [
            {
                "title": "NDAA FY24 Markup",
                "packageId": "CHRG-118hhrg52345",
                "collectionCode": "CHRG",
                "dateIssued": "2024-02-05",
                "governmentAuthor": ["Congress", "House of Representatives"],
            }
        ],
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(json=list_author_result)
        hearings = _source().hearings(118, "H.R. 2670")
    assert len(hearings) == 1
    # last non-empty list element wins — the most-specific name
    assert hearings[0].committee == "House of Representatives"
    assert hearings[0].title == "NDAA FY24 Markup"


def test_flatten_str_handles_string_list_none_and_other_types() -> None:
    """should coerce str / list / None / empty / unexpected to str | None per contract"""
    assert _flatten_str(None) is None
    assert _flatten_str("") is None
    assert _flatten_str("Senate Committee on Commerce") == "Senate Committee on Commerce"
    assert _flatten_str(["Congress", "House of Representatives"]) == "House of Representatives"
    # last NON-EMPTY string wins (skip trailing empties/None)
    assert _flatten_str(["Committee on Armed Services", "", None]) == "Committee on Armed Services"
    assert _flatten_str([]) is None
    assert _flatten_str([None, ""]) is None
    # unexpected types collapse to None rather than raising
    assert _flatten_str({"x": 1}) is None
    assert _flatten_str(42) is None


def test_hearings_escapes_double_quotes_in_citation() -> None:
    """should escape a double-quote in the citation so the search query stays well-formed"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.post("/search").respond(json=_fixture("search_chrg.json"))
        _source().hearings(118, 'the "AI" Act')
    posted = json.loads(route.calls.last.request.content)
    query = posted["query"]
    # the injected quote is escaped, not left dangling
    assert 'the \\"AI\\" Act' in query
    # exactly one unescaped boundary quote on each side → escaping kept quotes paired
    assert query == 'collection:CHRG AND congress:118 AND "the \\"AI\\" Act"'


# --- record_references -------------------------------------------------------


def test_record_references_maps_crec_search_results_to_floor_actions() -> None:
    """should POST the right query and map CREC results to FloorAction objects"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.post("/search").respond(json=_fixture("search_crec.json"))
        actions = _source().record_references(118, "H.R. 8818")
    assert route.call_count == 1
    posted = json.loads(route.calls.last.request.content)
    assert 'collection:CREC' in posted["query"]
    assert 'congress:118' in posted["query"]
    assert 'H.R. 8818' in posted["query"]

    assert len(actions) == 1
    assert isinstance(actions[0], FloorAction)
    assert actions[0].date == dt.date(2024, 12, 18)
    assert actions[0].congressional_record == "H8818 - House consideration and passage of H.R. 8818"
    # granuleId present → URL includes it
    assert actions[0].url == (
        "https://www.govinfo.gov/app/details/CREC-2024-12-18/CREC-2024-12-18-pt1-PgH8818"
    )
    assert actions[0].chamber is None  # filled downstream


def test_record_references_tolerant_when_optional_fields_missing() -> None:
    """should not raise when granuleId is absent from a CREC search result"""
    minimal_result = {
        "count": 1,
        "results": [
            {
                "title": "Some floor action",
                "packageId": "CREC-2024-06-01",
                "collectionCode": "CREC",
                "dateIssued": "2024-06-01",
            }
        ],
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(json=minimal_result)
        actions = _source().record_references(118, "H.R. 1")
    assert len(actions) == 1
    assert actions[0].url == "https://www.govinfo.gov/app/details/CREC-2024-06-01"


def test_record_references_escapes_double_quotes_in_citation() -> None:
    """should escape a double-quote in the citation so the search query stays well-formed"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.post("/search").respond(json=_fixture("search_crec.json"))
        _source().record_references(118, 'the "AI" Act')
    posted = json.loads(route.calls.last.request.content)
    query = posted["query"]
    # the injected quote is escaped, not left dangling
    assert 'the \\"AI\\" Act' in query
    # exactly one unescaped boundary quote on each side → escaping kept quotes paired
    assert query == 'collection:CREC AND congress:118 AND "the \\"AI\\" Act"'


# --- transport: retry and error mapping -------------------------------------


def test_get_json_retries_on_transient_server_error() -> None:
    """should retry a 5xx response and succeed on the following attempt"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.get(f"/related/{pkg_id}/PLAW")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=_fixture("related_plaw.json")),
        ]
        mock.get("/related/PLAW-118publ42/STATUTE").respond(json=_fixture("related_statute_empty.json"))
        enactment = _source().enacted_law(118, "HR", 8818)
    assert route.call_count == 2
    assert enactment is not None


def test_get_json_raises_rate_limit_error_on_429() -> None:
    """should surface a 429 GET response as a RateLimitError"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(429)
        with pytest.raises(RateLimitError):
            _source().enacted_law(118, "HR", 8818)


def test_related_treats_404_as_no_records() -> None:
    """should return None from enacted_law when the related lookup answers 404"""
    pkg_id = enrolled_bill_package_id(118, "HR", 9999)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(404)
        assert _source().enacted_law(118, "HR", 9999) is None


def test_get_json_raises_source_fetch_error_on_4xx() -> None:
    """should surface a non-404 4xx GET as SourceFetchError"""
    pkg_id = enrolled_bill_package_id(118, "HR", 9999)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(403)
        with pytest.raises(SourceFetchError):
            _source().enacted_law(118, "HR", 9999)


def test_package_summary_raises_not_found_on_404() -> None:
    """should surface a 404 on a non-related endpoint as SourceNotFoundError"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get("/packages/PLAW-118publ42/summary").respond(404)
        with pytest.raises(SourceNotFoundError):
            _source().package_summary("PLAW-118publ42")


def test_get_json_raises_source_fetch_error_after_retry_exhaustion() -> None:
    """should give up after max_attempts of 5xx and surface a SourceFetchError"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.get(f"/related/{pkg_id}/PLAW").respond(503)
        with pytest.raises(SourceFetchError):
            _source().enacted_law(118, "HR", 8818)
        assert route.call_count == 3  # max_attempts=3 passed to _source()


def test_post_json_raises_rate_limit_error_on_429() -> None:
    """should surface a 429 POST response as a RateLimitError"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(429)
        with pytest.raises(RateLimitError):
            _source().hearings(118, "H.R. 8818")


def test_post_json_retries_on_5xx_then_succeeds() -> None:
    """should retry a 5xx POST and succeed on the following attempt"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.post("/search")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=_fixture("search_chrg.json")),
        ]
        hearings = _source().hearings(118, "H.R. 8818")
    assert route.call_count == 2
    assert len(hearings) == 2


def test_post_json_raises_source_fetch_error_on_4xx() -> None:
    """should surface a non-429 4xx POST as SourceFetchError"""
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(403)
        with pytest.raises(SourceFetchError):
            _source().hearings(118, "H.R. 8818")


# --- fetch_statutes_at_large + enacted_law integration ----------------------


def test_fetch_statutes_at_large_maps_first_row_to_statutes_at_large() -> None:
    """should map STATUTE related row to StatutesAtLarge(citation, url)"""
    import respx

    from zwiadbrain.models import StatutesAtLarge
    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource

    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get("/related/PLAW-118publ31/STATUTE").respond(json=_fixture("related_statute.json"))
        result = GovInfoSource(api_key="k").fetch_statutes_at_large("PLAW-118publ31")
    assert isinstance(result, StatutesAtLarge)
    assert result.citation == "Statutes at Large Volume 138, Page 1234"
    assert result.url == "https://www.govinfo.gov/app/details/STATUTE-138-Pg1234"


def test_fetch_statutes_at_large_returns_none_on_empty_related() -> None:
    """should return None when /related/{plaw}/STATUTE has no results (fail-quiet)"""
    import respx

    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource

    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get("/related/PLAW-118publ99/STATUTE").respond(json=_fixture("related_statute_empty.json"))
        result = GovInfoSource(api_key="k").fetch_statutes_at_large("PLAW-118publ99")
    assert result is None


def test_enacted_law_now_populates_statutes_at_large() -> None:
    """should call fetch_statutes_at_large and attach the result to Enactment"""
    import respx

    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource, enrolled_bill_package_id

    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    plaw_results = {"results": [{"packageId": "PLAW-118publ42"}]}
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(json=plaw_results)
        mock.get("/related/PLAW-118publ42/STATUTE").respond(json=_fixture("related_statute.json"))
        result = GovInfoSource(api_key="k").enacted_law(118, "HR", 8818)
    assert result is not None
    assert result.statutes_at_large is not None
    assert result.statutes_at_large.citation == "Statutes at Large Volume 138, Page 1234"


# --- Retry-After and 429 fail-fast ------------------------------------------


def test_handle_response_parses_retry_after_onto_retryable() -> None:
    """should read Retry-After on a 503 and carry it on the GovInfo retry marker"""
    assert _retry_after_seconds(httpx.Response(503, headers={"Retry-After": "5"})) == 5.0
    assert _retry_after_seconds(httpx.Response(503)) is None
    assert _retry_after_seconds(httpx.Response(503, headers={"Retry-After": "later"})) is None


def test_get_json_honors_retry_after_then_succeeds() -> None:
    """should retry a 503-with-Retry-After GET and succeed using the header-driven wait"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.get(f"/related/{pkg_id}/PLAW")
        route.side_effect = [
            httpx.Response(503, headers={"Retry-After": "0"}),
            httpx.Response(200, json=_fixture("related_plaw.json")),
        ]
        mock.get("/related/PLAW-118publ42/STATUTE").respond(
            json=_fixture("related_statute_empty.json")
        )
        enactment = _source().enacted_law(118, "HR", 8818)
    assert route.call_count == 2
    assert enactment is not None


def test_429_stays_non_retryable_rate_limit_error() -> None:
    """should NOT retry a 429 (hourly key quota) — surface RateLimitError on the first hit"""
    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        route = mock.get(f"/related/{pkg_id}/PLAW").respond(429)
        with pytest.raises(RateLimitError):
            _source().enacted_law(118, "HR", 8818)
    assert route.call_count == 1  # fail-fast, no in-process retry of an hourly quota


def test_hearings_flattens_list_valued_granule_id() -> None:
    """should coerce a list-valued granuleId to its most-specific string before building the URL"""
    list_granule_result = {
        "count": 1,
        "results": [
            {
                "title": "Hearing on AI",
                "packageId": "CHRG-118shrg99001",
                "granuleId": ["CHRG-118shrg99001", "CHRG-118shrg99001-gpo1"],
                "collectionCode": "CHRG",
                "dateIssued": "2024-03-15",
            }
        ],
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(json=list_granule_result)
        hearings = _source().hearings(118, "H.R. 8818")
    assert len(hearings) == 1
    assert hearings[0].url == (
        "https://www.govinfo.gov/app/details/CHRG-118shrg99001/CHRG-118shrg99001-gpo1"
    )


def test_record_references_flattens_list_valued_granule_id() -> None:
    """should coerce a list-valued granuleId in a CREC result to its most-specific string"""
    list_granule_result = {
        "count": 1,
        "results": [
            {
                "title": "Floor consideration",
                "packageId": "CREC-2024-12-18",
                "granuleId": ["CREC-2024-12-18", "CREC-2024-12-18-pt1-PgH8818"],
                "collectionCode": "CREC",
                "dateIssued": "2024-12-18",
            }
        ],
    }
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.post("/search").respond(json=list_granule_result)
        actions = _source().record_references(118, "H.R. 8818")
    assert len(actions) == 1
    assert actions[0].url == (
        "https://www.govinfo.gov/app/details/CREC-2024-12-18/CREC-2024-12-18-pt1-PgH8818"
    )
