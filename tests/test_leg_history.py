"""Tests for the leg-history pipeline: assemble_spine, collect_leads, and identifier parsing.

Uses simple fake source objects — no live network calls.
"""

import datetime as dt

import pytest

from zwiadbrain.models import (
    Action,
    Bill,
    CommitteeReport,
    Enactment,
    FloorAction,
    Hearing,
    LegHistory,
    Statement,
    TextVersion,
    Vote,
)
from zwiadbrain.pipeline.leg_history import (
    _MIN_QUOTE_CHARS,  # pyright: ignore[reportPrivateUsage]
    GroundingResult,
    _parse_id,  # pyright: ignore[reportPrivateUsage]
    _quote_present,  # pyright: ignore[reportPrivateUsage]
    assemble_spine,
    collect_leads,
    ground_items,
)

# ---------------------------------------------------------------------------
# Fake sources
# ---------------------------------------------------------------------------


class _FakeCongress:
    """Minimal Congress source fake: returns canned Vote list."""

    def __init__(self, votes: list[Vote] | None = None) -> None:
        self._votes = votes or []
        self.calls: list[str] = []

    def recorded_votes(self, native_id: str) -> list[Vote]:
        self.calls.append(native_id)
        return self._votes


class _FakeGovInfo:
    """Minimal GovInfo source fake: returns canned leg-history model lists."""

    def __init__(
        self,
        *,
        committee_reports: list[CommitteeReport] | None = None,
        enacted_law: Enactment | None = None,
        hearings: list[Hearing] | None = None,
        floor_actions: list[FloorAction] | None = None,
    ) -> None:
        self._committee_reports = committee_reports or []
        self._enacted_law = enacted_law
        self._hearings = hearings or []
        self._floor_actions = floor_actions or []

    def committee_reports(
        self, congress: int, bill_type: str, number: str
    ) -> list[CommitteeReport]:
        return self._committee_reports

    def enacted_law(self, congress: int, bill_type: str, number: str) -> Enactment | None:
        return self._enacted_law

    def hearings(self, congress: int, citation: str) -> list[Hearing]:
        return self._hearings

    def record_references(self, congress: int, citation: str) -> list[FloorAction]:
        return self._floor_actions


# ---------------------------------------------------------------------------
# Helpers to build minimal Bills
# ---------------------------------------------------------------------------


def _enacted_bill(
    *,
    bill_id: str = "118-hr-9020",
    bill_number: str = "H.R. 9020",
    public_law: str | None = "118-100",
    actions: list[Action] | None = None,
    text_versions: list[TextVersion] | None = None,
) -> Bill:
    if actions is None:
        actions = [
            Action(
                date=dt.date(2024, 12, 20),
                text="Became Public Law No: 118-100.",
                action_type="BecameLaw",
            ),
            Action(
                date=dt.date(2024, 12, 18),
                text="Signed by President.",
                action_type="President",
            ),
            Action(
                date=dt.date(2024, 6, 26),
                text="Introduced in House.",
                action_type="IntroReferral",
            ),
        ]
    if text_versions is None:
        text_versions = [
            TextVersion(code="Enrolled Bill", date=dt.date(2024, 12, 1)),
            TextVersion(code="Introduced in House", date=dt.date(2024, 6, 26)),
        ]
    return Bill(
        id=bill_id,
        jurisdiction="US",
        title="Test Accountability Act",
        bill_number=bill_number,
        congress="118",
        enacted=True,
        public_law=public_law,
        actions=actions,
        text_versions=text_versions,
        sponsors=["Rep. Smith, Jane [D-CA-1]"],
        related_bills=["S. 2024 (118th)"],
        introduced_date=dt.date(2024, 6, 26),
        latest_action_date=dt.date(2024, 12, 20),
    )


# ---------------------------------------------------------------------------
# assemble_spine — field sourcing
# ---------------------------------------------------------------------------


def test_assemble_spine_versions_come_from_bill() -> None:
    """should populate versions from bill.text_versions"""
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo())
    assert isinstance(spine, LegHistory)
    assert spine.versions == bill.text_versions
    assert len(spine.versions) == 2
    assert spine.versions[0].code == "Enrolled Bill"


def test_assemble_spine_committee_reports_come_from_govinfo() -> None:
    """should populate committee_reports from govinfo.committee_reports"""
    reports = [CommitteeReport(citation="H. Rept. 118-712", url="https://example.com/rpt")]
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(committee_reports=reports))
    assert spine.committee_reports == reports


def test_assemble_spine_votes_come_from_congress_source() -> None:
    """should populate votes from congress_source.recorded_votes"""
    votes = [Vote(date=dt.date(2024, 7, 15), chamber="House", roll_call_url="https://clerk.house.gov/vote/1")]
    congress = _FakeCongress(votes=votes)
    bill = _enacted_bill()
    spine = assemble_spine(bill, congress, _FakeGovInfo())
    assert spine.votes == votes
    assert congress.calls == ["118/hr/9020"]


def test_assemble_spine_floor_consideration_comes_from_govinfo() -> None:
    """should populate floor_consideration from govinfo (url-bearing items only)"""
    floor = [FloorAction(
        date=dt.date(2024, 12, 18),
        congressional_record="H8818",
        url="https://www.govinfo.gov/app/details/CREC-2024-12-18",
    )]
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(floor_actions=floor))
    assert spine.floor_consideration == floor


def test_assemble_spine_passes_correct_identifiers_to_govinfo() -> None:
    """should derive congress, bill_type, number from bill.id and pass them correctly"""
    # track what args govinfo receives
    received: dict[str, object] = {}

    class _TrackingGovInfo(_FakeGovInfo):
        def committee_reports(  # type: ignore[override]
            self, congress: int, bill_type: str, number: str
        ) -> list[CommitteeReport]:
            received["committee_reports"] = (congress, bill_type, number)
            return []

        def enacted_law(  # type: ignore[override]
            self, congress: int, bill_type: str, number: str
        ) -> Enactment | None:
            received["enacted_law"] = (congress, bill_type, number)
            return None

        def record_references(  # type: ignore[override]
            self, congress: int, citation: str
        ) -> list[FloorAction]:
            received["record_references"] = (congress, citation)
            return []

    bill = _enacted_bill(bill_id="118-hr-9020", bill_number="H.R. 9020")
    assemble_spine(bill, _FakeCongress(), _TrackingGovInfo())

    assert received["committee_reports"] == (118, "hr", "9020")
    assert received["enacted_law"] == (118, "hr", "9020")
    assert received["record_references"] == (118, "H.R. 9020")


# ---------------------------------------------------------------------------
# assemble_spine — enactment merging
# ---------------------------------------------------------------------------


def test_assemble_spine_enactment_merges_govinfo_law_with_signed_date() -> None:
    """should set enactment.date_signed from bill actions, use govinfo for url/statutes"""
    law = Enactment(
        public_law="118-100",
        url="https://www.govinfo.gov/app/details/PLAW-118publ100",
        statutes_at_large=None,
        date_signed=None,
    )
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=law))
    assert spine.enactment is not None
    # signed date extracted from "Signed by President." action
    assert spine.enactment.date_signed == dt.date(2024, 12, 18)
    # public_law from govinfo (prefers govinfo over bill.public_law)
    assert spine.enactment.public_law == "118-100"
    assert spine.enactment.url == "https://www.govinfo.gov/app/details/PLAW-118publ100"
    assert spine.enactment.statutes_at_large is None


def test_assemble_spine_enactment_falls_back_to_bill_public_law_when_govinfo_has_none() -> None:
    """should use bill.public_law when govinfo returns None for enacted_law"""
    bill = _enacted_bill(public_law="118-42")
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=None))
    assert spine.enactment is not None
    assert spine.enactment.public_law == "118-42"
    assert spine.enactment.url is None
    assert spine.enactment.statutes_at_large is None


def test_assemble_spine_enactment_is_none_when_nothing_available() -> None:
    """should leave enactment=None when govinfo returns None and bill has no public_law"""
    bill = _enacted_bill(public_law=None, actions=[])
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=None))
    assert spine.enactment is None


def test_assemble_spine_enactment_signed_date_from_became_public_law_action() -> None:
    """should extract signed date from 'Became Public Law' action (case-insensitive)"""
    actions = [
        Action(date=dt.date(2024, 12, 20), text="became public law No: 118-100.", action_type="BecameLaw"),  # noqa: E501
        Action(date=dt.date(2024, 6, 26), text="Introduced in House.", action_type="IntroReferral"),
    ]
    bill = _enacted_bill(actions=actions)
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=None))
    assert spine.enactment is not None
    assert spine.enactment.date_signed == dt.date(2024, 12, 20)


def test_assemble_spine_enactment_govinfo_public_law_preferred_over_bill() -> None:
    """should prefer govinfo public_law over bill.public_law when both are present"""
    law = Enactment(
        public_law="118-200",  # different from bill's public_law
        url="https://govinfo.example",
        statutes_at_large="138 Stat. 1234",
        date_signed=None,
    )
    bill = _enacted_bill(public_law="118-100")  # bill has its own
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=law))
    assert spine.enactment is not None
    assert spine.enactment.public_law == "118-200"  # govinfo wins
    assert spine.enactment.statutes_at_large == "138 Stat. 1234"


def test_assemble_spine_enactment_url_falls_back_to_congress_source_when_govinfo_has_no_url() -> (  # noqa: E501
    None
):
    """should set enactment.url to bill.sources['Congress.gov'] when govinfo url=None

    I1 enactment-URL backstop: a bill with a Congress.gov page URL always provides a
    clickable source link on the enactment row, even when GovInfo has no PLAW URL.
    """
    congress_url = "https://www.congress.gov/bill/118th-congress/house-bill/9020"
    law = Enactment(
        public_law="118-100",
        url=None,  # GovInfo has no PLAW URL
        statutes_at_large=None,
        date_signed=None,
    )
    bill = _enacted_bill()
    # Inject the Congress.gov source URL via the bill's sources dict.
    # CongressSource always populates sources["Congress.gov"] on enriched bills.
    bill = bill.model_copy(update={"sources": {"Congress.gov": congress_url}})
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=law))
    assert spine.enactment is not None
    assert spine.enactment.url == congress_url


def test_assemble_spine_enactment_url_govinfo_preferred_over_congress_source() -> None:
    """should use govinfo url when both govinfo and bill.sources have a URL (govinfo wins)"""
    govinfo_url = "https://www.govinfo.gov/app/details/PLAW-118publ100"
    congress_url = "https://www.congress.gov/bill/118th-congress/house-bill/9020"
    law = Enactment(
        public_law="118-100",
        url=govinfo_url,
        statutes_at_large=None,
        date_signed=None,
    )
    bill = _enacted_bill()
    bill = bill.model_copy(update={"sources": {"Congress.gov": congress_url}})
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(enacted_law=law))
    assert spine.enactment is not None
    assert spine.enactment.url == govinfo_url  # govinfo URL takes priority


def test_assemble_spine_floor_consideration_drops_link_less_items() -> None:
    """should exclude floor actions that have no URL (title-only CREC hits)

    I1 floor-URL filter: a CREC hit without a URL is just a title — it cannot be
    verified and matches the hearings/statements no-link-no-persist policy.
    """
    floor_with_url = FloorAction(
        date=dt.date(2024, 12, 18),
        congressional_record="H8818",
        url="https://www.govinfo.gov/app/details/CREC-2024-12-18",
    )
    floor_no_url = FloorAction(
        date=dt.date(2024, 12, 17),
        congressional_record="H8817",
        url=None,  # title-only hit — must be filtered out
    )
    bill = _enacted_bill()
    spine = assemble_spine(
        bill, _FakeCongress(), _FakeGovInfo(floor_actions=[floor_with_url, floor_no_url])
    )
    assert len(spine.floor_consideration) == 1
    assert spine.floor_consideration[0] is floor_with_url


def test_assemble_spine_floor_consideration_empty_when_all_link_less() -> None:
    """should produce an empty floor_consideration list when every CREC item has no URL"""
    floor_no_url = FloorAction(
        date=dt.date(2024, 12, 18),
        congressional_record="H8818",
        url=None,
    )
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(floor_actions=[floor_no_url]))
    assert spine.floor_consideration == []


# ---------------------------------------------------------------------------
# _signed_date — action scanning
# ---------------------------------------------------------------------------


def test_signed_date_found_from_signed_by_president_action() -> None:
    """should find the date of 'Signed by President' action"""
    # Tested indirectly through assemble_spine's enactment
    actions = [
        Action(date=dt.date(2024, 12, 18), text="Signed by President.", action_type="President"),
    ]
    bill = _enacted_bill(actions=actions, public_law="118-100")
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo())
    assert spine.enactment is not None
    assert spine.enactment.date_signed == dt.date(2024, 12, 18)


def test_signed_date_returns_none_when_no_enactment_action() -> None:
    """should return None when no 'Signed by President'/'Became Public Law' action exists"""
    actions = [
        Action(date=dt.date(2024, 6, 26), text="Introduced in House.", action_type="IntroReferral"),
        Action(date=dt.date(2024, 7, 15), text="Passed/agreed to in House.", action_type="Floor"),
    ]
    bill = _enacted_bill(actions=actions, public_law="118-100")
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo())
    assert spine.enactment is not None
    assert spine.enactment.date_signed is None


def test_signed_date_case_insensitive_match() -> None:
    """should match enactment action text case-insensitively"""
    actions = [
        Action(date=dt.date(2024, 12, 20), text="BECAME PUBLIC LAW NO: 118-100.", action_type="BecameLaw"),  # noqa: E501
    ]
    bill = _enacted_bill(actions=actions, public_law="118-100")
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo())
    assert spine.enactment is not None
    assert spine.enactment.date_signed == dt.date(2024, 12, 20)


# ---------------------------------------------------------------------------
# assemble_spine — researcher fields left at defaults
# ---------------------------------------------------------------------------


def test_assemble_spine_leaves_researcher_fields_at_defaults() -> None:
    """should leave conference, narrative, hearings, statements at their defaults"""
    bill = _enacted_bill()
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo())
    assert spine.conference is None
    assert spine.narrative is None
    assert spine.hearings == []
    assert spine.statements == []


# ---------------------------------------------------------------------------
# collect_leads
# ---------------------------------------------------------------------------


def test_collect_leads_returns_dict_with_core_fields() -> None:
    """should return a dict with id, congress, citation, title, sponsors, related_bills"""
    bill = _enacted_bill()
    leads = collect_leads(bill, _FakeGovInfo())
    assert leads["id"] == "118-hr-9020"
    assert leads["congress"] == "118"
    assert leads["citation"] == "H.R. 9020"
    assert leads["title"] == "Test Accountability Act"
    assert leads["sponsors"] == ["Rep. Smith, Jane [D-CA-1]"]
    assert leads["related_bills"] == ["S. 2024 (118th)"]


def test_collect_leads_congress_comes_from_parsed_id_not_bill_field() -> None:
    """should derive congress from bill.id, ignoring a divergent bill.congress field"""
    # Construct a bill whose id-derived congress (117) differs from its congress field.
    bill = Bill(
        id="117-hr-9020",
        jurisdiction="US",
        title="Test Act",
        bill_number="H.R. 9020",
        congress="999",  # deliberately inconsistent with the id
    )
    leads = collect_leads(bill, _FakeGovInfo())
    # the leads congress must match the id-derived value, not bill.congress
    assert leads["congress"] == "117"


def test_collect_leads_dates_as_isoformat() -> None:
    """should serialize introduced_date and latest_action_date as isoformat strings"""
    bill = _enacted_bill()
    leads = collect_leads(bill, _FakeGovInfo())
    assert leads["introduced_date"] == "2024-06-26"
    assert leads["latest_action_date"] == "2024-12-20"


def test_collect_leads_dates_as_none_when_absent() -> None:
    """should use None for dates that are not set on the bill"""
    bill = Bill(
        id="118-hr-9020",
        jurisdiction="US",
        title="Test Act",
        bill_number="H.R. 9020",
        congress="118",
        introduced_date=None,
        latest_action_date=None,
    )
    leads = collect_leads(bill, _FakeGovInfo())
    assert leads["introduced_date"] is None
    assert leads["latest_action_date"] is None


def test_collect_leads_hearings_as_dicts() -> None:
    """should include hearings from govinfo as a list of dicts (model_dump)"""
    hearings = [
        Hearing(
            title="Hearing on AI Act",
            committee="House Judiciary",
            date=dt.date(2024, 3, 15),
            citation="CHRG-118hhrg54321",
            url="https://www.govinfo.gov/app/details/CHRG-118hhrg54321",
        )
    ]
    bill = _enacted_bill()
    leads = collect_leads(bill, _FakeGovInfo(hearings=hearings))
    assert "hearings" in leads
    hearing_dicts: list[dict[str, object]] = leads["hearings"]  # type: ignore[assignment]
    assert len(hearing_dicts) == 1
    assert hearing_dicts[0]["title"] == "Hearing on AI Act"
    assert hearing_dicts[0]["committee"] == "House Judiciary"
    assert hearing_dicts[0]["date"] == "2024-03-15"
    assert "url" in hearing_dicts[0]


def test_collect_leads_hearings_empty_when_none() -> None:
    """should return an empty hearings list when govinfo returns no hearings"""
    bill = _enacted_bill()
    leads = collect_leads(bill, _FakeGovInfo(hearings=[]))
    assert leads["hearings"] == []


def test_collect_leads_does_not_include_spine_fields() -> None:
    """should not include statements, narrative, or spine fields — these are researcher's job"""
    bill = _enacted_bill()
    leads = collect_leads(bill, _FakeGovInfo())
    assert "statements" not in leads
    assert "narrative" not in leads
    assert "votes" not in leads
    assert "committee_reports" not in leads
    assert "floor_consideration" not in leads
    assert "enactment" not in leads


def test_collect_leads_hearings_are_not_in_spine() -> None:
    """hearings in collect_leads dict are unverified leads, not inserted into spine"""
    hearings = [Hearing(title="Unverified Hearing", url=None)]
    bill = _enacted_bill()
    # spine should have empty hearings regardless
    spine = assemble_spine(bill, _FakeCongress(), _FakeGovInfo(hearings=hearings))
    assert spine.hearings == []
    # leads dict should have the hearing
    leads = collect_leads(bill, _FakeGovInfo(hearings=hearings))
    assert len(leads["hearings"]) == 1


# ---------------------------------------------------------------------------
# identifier parsing
# ---------------------------------------------------------------------------


def test_identifier_parsing_standard_hr_bill() -> None:
    """should parse '118-hr-9020' into congress=118, type='hr', number='9020' for native_id"""
    votes = [Vote(date=dt.date(2024, 7, 15), chamber="House", roll_call_url="https://example.com/1")]
    congress = _FakeCongress(votes=votes)
    bill = _enacted_bill(bill_id="118-hr-9020")
    assemble_spine(bill, congress, _FakeGovInfo())
    # native_id format: "{congress}/{type}/{number}"
    assert congress.calls == ["118/hr/9020"]


def test_identifier_parsing_senate_bill() -> None:
    """should parse '118-s-1234' into native_id '118/s/1234' and citation from bill_number"""
    received: dict[str, object] = {}

    class _TrackGovInfo(_FakeGovInfo):
        def record_references(  # type: ignore[override]
            self, congress: int, citation: str
        ) -> list[FloorAction]:
            received["congress"] = congress
            received["citation"] = citation
            return []

    bill = Bill(
        id="118-s-1234",
        jurisdiction="US",
        title="Senate Bill",
        bill_number="S. 1234",
        congress="118",
    )
    congress = _FakeCongress()
    assemble_spine(bill, congress, _TrackGovInfo())
    assert congress.calls == ["118/s/1234"]
    assert received["congress"] == 118
    assert received["citation"] == "S. 1234"


def test_identifier_parsing_joint_resolution() -> None:
    """should parse '118-hjres-45' preserving multi-char type segment"""
    congress = _FakeCongress()
    bill = Bill(
        id="118-hjres-45",
        jurisdiction="US",
        title="Joint Resolution",
        bill_number="H.J.Res. 45",
        congress="118",
    )
    assemble_spine(bill, congress, _FakeGovInfo())
    assert congress.calls == ["118/hjres/45"]


# ---------------------------------------------------------------------------
# _parse_id — direct validation
# ---------------------------------------------------------------------------


def test_parse_id_parses_well_formed_ids() -> None:
    """should parse well-formed ids into (congress:int, type, number)"""
    assert _parse_id("118-hr-9020") == (118, "hr", "9020")
    assert _parse_id("118-hjres-1") == (118, "hjres", "1")
    assert _parse_id("117-s-2024") == (117, "s", "2024")


def test_parse_id_raises_on_missing_number_segment() -> None:
    """should raise ValueError when the id has only two segments"""
    with pytest.raises(ValueError, match="bill.id must be"):
        _parse_id("118-hr")


def test_parse_id_raises_on_missing_type_segment() -> None:
    """should raise ValueError when the id has no type segment (two segments only)"""
    with pytest.raises(ValueError, match="bill.id must be"):
        _parse_id("118-9020")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_statement(
    *,
    speaker: str = "Rep. Smith",
    quote: str = "This bill is important.",
    source_url: str = "https://example.com/record",
    verified: bool = False,
) -> Statement:
    return Statement(
        speaker=speaker,
        role="member",
        quote=quote,
        source_url=source_url,
        source_type="CREC",
        verified=verified,
    )


def _make_hearing(
    *,
    title: str = "Hearing on AI Act",
    url: str | None = "https://example.com/hearing",
) -> Hearing:
    return Hearing(title=title, url=url)


class _FakeFetch:
    """Fetch callable backed by a url->response dict. Missing urls return (0, '')."""

    def __init__(self, url_map: dict[str, tuple[int, str]]) -> None:
        self._url_map = url_map

    def __call__(self, url: str) -> tuple[int, str]:
        return self._url_map.get(url, (0, ""))


def _fake_fetch(url_map: dict[str, tuple[int, str]]) -> _FakeFetch:
    """Convenience constructor for _FakeFetch."""
    return _FakeFetch(url_map)


# ---------------------------------------------------------------------------
# _quote_present — helper unit tests
# ---------------------------------------------------------------------------


def test_quote_present_exact_match() -> None:
    """should return True when quote appears verbatim in page text"""
    assert _quote_present("hello world", "prefix hello world suffix") is True


def test_quote_present_whitespace_normalization() -> None:
    """should match quote with collapsed whitespace against page with extra spaces/newlines"""
    assert _quote_present("the AI Act", "... the\n  AI   Act ...") is True


def test_quote_present_curly_quote_normalization() -> None:
    """should match straight-quote query against curly-quote page text (and vice versa)"""
    # Use chr() so no non-ASCII bytes appear in this source file.
    LDQ = chr(0x201C)  # LEFT DOUBLE QUOTATION MARK
    RDQ = chr(0x201D)  # RIGHT DOUBLE QUOTATION MARK

    # page has curly double quotes; quote uses straight ASCII double-quotes
    page_curly = "prefix " + LDQ + "AI" + RDQ + " Act suffix"
    assert _quote_present('"AI" Act', page_curly) is True

    # page has straight ASCII double-quotes; quote has curly double-quotes
    page_straight = 'prefix "AI" Act suffix'
    assert _quote_present(LDQ + "AI" + RDQ + " Act", page_straight) is True


def test_quote_present_curly_apostrophe_normalization() -> None:
    """should normalize curly apostrophes on both sides"""
    # right single quotation mark U+2019 → straight apostrophe
    assert _quote_present("it’s important", "it's important here") is True
    assert _quote_present("it's important", "it’s important here") is True


def test_quote_present_empty_quote_never_matches() -> None:
    """should return False for an empty or blank-only quote"""
    assert _quote_present("", "any page text") is False
    assert _quote_present("   ", "any page text") is False


def test_quote_present_case_sensitive() -> None:
    """should be case-sensitive — 'AI Act' does not match 'ai act'"""
    assert _quote_present("AI Act", "ai act") is False


def test_quote_present_not_in_page() -> None:
    """should return False when quote is not in page text"""
    assert _quote_present("missing phrase", "completely different content") is False


# ---------------------------------------------------------------------------
# ground_items — statement gate
# ---------------------------------------------------------------------------


def test_ground_items_statement_kept_when_all_gates_pass() -> None:
    """should keep statement and set verified=True when url 200, quote present, verifier True"""
    stmt = _make_statement(quote="This bill is important.", verified=False)
    fetch = _fake_fetch({"https://example.com/record": (200, "This bill is important. More text.")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 1
    assert result.statements[0].verified is True
    assert len(result.dropped) == 0


def test_ground_items_model_copy_does_not_mutate_original() -> None:
    """should not mutate the original statement object — verified stays False on input"""
    stmt = _make_statement(verified=False)
    fetch = _fake_fetch({"https://example.com/record": (200, "This bill is important. Extra.")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    # Original is unchanged
    assert stmt.verified is False
    # Returned copy has verified=True
    assert result.statements[0].verified is True


def test_ground_items_statement_dropped_when_verifier_false() -> None:
    """should drop statement when url 200, quote present, but verifier returns False"""
    stmt = _make_statement()
    fetch = _fake_fetch({"https://example.com/record": (200, "This bill is important. Extra.")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: False})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "verifier" in result.dropped[0].reason


def test_ground_items_statement_dropped_when_quote_absent() -> None:
    """should drop statement when url 200 but quote not found on page"""
    stmt = _make_statement(quote="This bill is important.")
    fetch = _fake_fetch({"https://example.com/record": (200, "completely unrelated page content")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "quote not found" in result.dropped[0].reason


def test_ground_items_statement_dropped_when_url_returns_404() -> None:
    """should drop statement when source url returns 404"""
    stmt = _make_statement()
    fetch = _fake_fetch({"https://example.com/record": (404, "")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "404" in result.dropped[0].reason


def test_ground_items_statement_dropped_when_url_unreachable() -> None:
    """should drop statement when source url returns status 0 (connection error)"""
    stmt = _make_statement()
    fetch = _fake_fetch({})  # all urls → (0, "")
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "0" in result.dropped[0].reason


def test_ground_items_statement_dropped_when_verifier_index_missing() -> None:
    """should treat a missing verifier index as not-verified and drop the statement"""
    stmt = _make_statement()
    fetch = _fake_fetch({"https://example.com/record": (200, "This bill is important. Extra.")})
    # verifier_verdicts is empty — index 0 is missing
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "verifier" in result.dropped[0].reason


def test_ground_items_dropped_statement_has_correct_kind_and_identifier() -> None:
    """should record kind='statement' and identifier '<speaker>: <first 50 chars>' in DroppedItem"""
    stmt = _make_statement(speaker="Sen. Jones", quote="A" * 60)
    fetch = _fake_fetch({"https://example.com/record": (404, "")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={})
    dropped = result.dropped[0]
    assert dropped.kind == "statement"
    assert dropped.identifier.startswith("Sen. Jones: ")
    assert len(dropped.identifier) <= len("Sen. Jones: ") + 50


# ---------------------------------------------------------------------------
# ground_items — hearing gate
# ---------------------------------------------------------------------------


def test_ground_items_hearing_kept_when_url_200() -> None:
    """should keep hearing unchanged when url resolves to 200"""
    hearing = _make_hearing(url="https://example.com/hearing")
    fetch = _fake_fetch({"https://example.com/hearing": (200, "")})
    result = ground_items([], [hearing], fetch=fetch, verifier_verdicts={})
    assert len(result.hearings) == 1
    assert result.hearings[0] is hearing
    assert len(result.dropped) == 0


def test_ground_items_hearing_dropped_when_url_404() -> None:
    """should drop hearing when url returns 404"""
    hearing = _make_hearing(url="https://example.com/hearing")
    fetch = _fake_fetch({"https://example.com/hearing": (404, "")})
    result = ground_items([], [hearing], fetch=fetch, verifier_verdicts={})
    assert len(result.hearings) == 0
    assert len(result.dropped) == 1
    assert "404" in result.dropped[0].reason


def test_ground_items_hearing_dropped_when_no_url() -> None:
    """should drop hearing that has no source url with the 'hearing has no source url' reason"""
    hearing = _make_hearing(url=None)
    fetch = _fake_fetch({})
    result = ground_items([], [hearing], fetch=fetch, verifier_verdicts={})
    assert len(result.hearings) == 0
    assert len(result.dropped) == 1
    assert result.dropped[0].reason == "hearing has no source url"


def test_ground_items_dropped_hearing_has_correct_kind_and_identifier() -> None:
    """should record kind='hearing' and identifier=hearing.title in DroppedItem"""
    hearing = _make_hearing(title="Privacy Oversight Hearing", url="https://example.com/h")
    fetch = _fake_fetch({"https://example.com/h": (503, "")})
    result = ground_items([], [hearing], fetch=fetch, verifier_verdicts={})
    dropped = result.dropped[0]
    assert dropped.kind == "hearing"
    assert dropped.identifier == "Privacy Oversight Hearing"


# ---------------------------------------------------------------------------
# ground_items — mixed and edge cases
# ---------------------------------------------------------------------------


def test_ground_items_gates_checked_in_order_url_first() -> None:
    """first gate failure (url) must be the recorded reason, not a later gate"""
    # url will 404 — even though the quote *would* be present and verifier is True,
    # the reason must be about the status code, not about the quote
    stmt = _make_statement(quote="This bill is important.")
    fetch = _fake_fetch({"https://example.com/record": (404, "This bill is important.")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.dropped) == 1
    assert "404" in result.dropped[0].reason
    assert "quote" not in result.dropped[0].reason


def test_ground_items_dropped_list_contains_all_rejected_items() -> None:
    """dropped list should contain one DroppedItem per rejected statement or hearing"""
    stmt1 = _make_statement(speaker="A", source_url="https://example.com/a")
    stmt2 = _make_statement(speaker="B", source_url="https://example.com/b")
    hearing = _make_hearing(url=None)
    fetch = _fake_fetch({
        "https://example.com/a": (404, ""),
        "https://example.com/b": (200, "This bill is important. Extra."),
    })
    # stmt1: 404 -> dropped; stmt2: 200+quote present but verifier missing -> dropped
    # hearing: no url -> dropped
    result = ground_items([stmt1, stmt2], [hearing], fetch=fetch, verifier_verdicts={})
    assert len(result.dropped) == 3
    kinds = [d.kind for d in result.dropped]
    assert kinds.count("statement") == 2
    assert kinds.count("hearing") == 1


def test_ground_items_returns_grounding_result_type() -> None:
    """ground_items should return a GroundingResult instance with empty tuple fields"""
    result = ground_items([], [], fetch=_fake_fetch({}), verifier_verdicts={})
    assert isinstance(result, GroundingResult)
    assert result.statements == ()
    assert result.hearings == ()
    assert result.dropped == ()


def test_ground_items_result_fields_are_immutable_tuples() -> None:
    """result fields must be tuples so nothing can be appended past the gate"""
    stmt = _make_statement(quote="This bill is important.")
    hearing = _make_hearing(url="https://example.com/hearing")
    fetch = _fake_fetch({
        "https://example.com/record": (200, "This bill is important. Extra."),
        "https://example.com/hearing": (200, ""),
    })
    result = ground_items([stmt], [hearing], fetch=fetch, verifier_verdicts={0: True})
    assert isinstance(result.statements, tuple)
    assert isinstance(result.hearings, tuple)
    assert isinstance(result.dropped, tuple)
    # A tuple has no append; trying to mutate must raise AttributeError.
    with pytest.raises(AttributeError):
        result.statements.append(stmt)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ground_items — minimum quote length (gate 0)
# ---------------------------------------------------------------------------


def test_ground_items_statement_dropped_when_quote_too_short() -> None:
    """should drop a trivially short quote with the too-short reason, before any fetch"""
    short = _make_statement(quote="no")
    # Even though the page contains the quote and the verifier says True,
    # gate 0 (min length) drops it first — and no fetch entry is needed.
    fetch = _fake_fetch({"https://example.com/record": (200, "no")})
    result = ground_items([short], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "too short" in result.dropped[0].reason
    assert "2 chars" in result.dropped[0].reason


def test_ground_items_min_length_uses_normalized_length() -> None:
    """should measure length after normalization (whitespace collapse), not raw length"""
    # Raw string is long (lots of whitespace) but normalizes to "the AI Act" = 10 chars.
    padded = _make_statement(quote="the\n\n   AI        Act")
    fetch = _fake_fetch({"https://example.com/record": (200, "the AI Act here")})
    result = ground_items([padded], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "too short" in result.dropped[0].reason
    assert "10 chars" in result.dropped[0].reason


def test_ground_items_min_length_floor_runs_before_fetch() -> None:
    """gate 0 must run before fetch — a short quote drops even if its url 404s"""
    short = _make_statement(quote="ok")
    fetch = _fake_fetch({})  # url unreachable (status 0)
    result = ground_items([short], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.dropped) == 1
    # The reason is about length, not the (unreached) url status.
    assert "too short" in result.dropped[0].reason
    assert "status" not in result.dropped[0].reason


def test_ground_items_quote_at_min_length_floor_passes() -> None:
    """a quote with exactly _MIN_QUOTE_CHARS normalized chars passes gate 0"""
    quote = "A" * _MIN_QUOTE_CHARS
    stmt = _make_statement(quote=quote)
    fetch = _fake_fetch({"https://example.com/record": (200, f"prefix {quote} suffix")})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 1
    assert result.statements[0].verified is True
    assert len(result.dropped) == 0


def test_ground_items_quote_just_below_floor_dropped() -> None:
    """a quote one char below _MIN_QUOTE_CHARS is dropped as too short"""
    quote = "A" * (_MIN_QUOTE_CHARS - 1)
    stmt = _make_statement(quote=quote)
    fetch = _fake_fetch({"https://example.com/record": (200, quote)})
    result = ground_items([stmt], [], fetch=fetch, verifier_verdicts={0: True})
    assert len(result.statements) == 0
    assert len(result.dropped) == 1
    assert "too short" in result.dropped[0].reason
