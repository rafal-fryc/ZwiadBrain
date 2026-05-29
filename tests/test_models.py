"""Tests for ZwiadBrain pydantic data models.

These pin the behavioural contract that matters downstream: the discriminated
union routes by `type`, required identifiers are enforced, list fields default
empty, and a parsed item round-trips through `model_dump`.
"""

import datetime as dt

import pytest
from pydantic import ValidationError

from zwiadbrain.models import (
    Bill,
    CommentarySource,
    Enactment,
    EnforcementAction,
    Hearing,
    LegHistory,
    Statement,
    parse_wiki_item,
)


def test_parse_wiki_item_routes_bill_by_type_discriminator() -> None:
    """should return a Bill when type == 'bill'"""
    item = parse_wiki_item(
        {
            "id": "us-ca-sb-362",
            "type": "bill",
            "jurisdiction": "US-CA",
            "title": "California Delete Act",
            "bill_number": "SB 362",
        }
    )
    assert isinstance(item, Bill)
    assert item.bill_number == "SB 362"


def test_parse_wiki_item_routes_enforcement_by_type_discriminator() -> None:
    """should return an EnforcementAction when type == 'enforcement'"""
    item = parse_wiki_item(
        {
            "id": "ftc-betterhelp",
            "type": "enforcement",
            "jurisdiction": "US",
            "title": "FTC v. BetterHelp",
            "agency": "FTC",
        }
    )
    assert isinstance(item, EnforcementAction)
    assert item.agency == "FTC"


def test_bill_requires_bill_number() -> None:
    """should reject a bill with no bill_number"""
    with pytest.raises(ValidationError):
        Bill.model_validate({"id": "x", "jurisdiction": "US-CA", "title": "t"})


def test_commentary_source_rejects_out_of_range_confidence() -> None:
    """should reject a confidence above 1.0"""
    with pytest.raises(ValidationError):
        CommentarySource.model_validate(
            {
                "path": "wiki/regulation-x.md",
                "slug": "regulation-x",
                "content_hash": "deadbeef",
                "matched_by": "llm",
                "confidence": 1.5,
            }
        )


def test_enforcement_requires_agency() -> None:
    """should reject an enforcement action with no agency"""
    with pytest.raises(ValidationError):
        EnforcementAction.model_validate({"id": "x", "jurisdiction": "US", "title": "t"})


def test_commentary_sources_default_to_empty_list() -> None:
    """should default commentary_sources to an empty list"""
    bill = Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1")
    assert bill.commentary_sources == []


def test_commentary_source_rejects_unknown_matched_by() -> None:
    """should constrain matched_by to the known matching strategies"""
    with pytest.raises(ValidationError):
        CommentarySource.model_validate(
            {
                "path": "wiki/regulation-x.md",
                "slug": "regulation-x",
                "content_hash": "deadbeef",
                "matched_by": "telepathy",
                "confidence": 1.0,
            }
        )


def test_list_defaults_are_not_shared_between_instances() -> None:
    """should give each instance its own list, not a shared mutable default"""
    a = Bill(id="us-ca-sb-1", jurisdiction="US-CA", title="t", bill_number="SB 1")
    b = Bill(id="us-ca-sb-2", jurisdiction="US-CA", title="t", bill_number="SB 2")
    a.topics.append("ai")
    assert b.topics == []


def test_wiki_item_round_trips_through_dump_and_parse() -> None:
    """should survive model_dump -> parse_wiki_item preserving its concrete type"""
    bill = Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1")
    again = parse_wiki_item(bill.model_dump())
    assert isinstance(again, Bill)
    assert again == bill


# ---------------------------------------------------------------------------
# Hearing
# ---------------------------------------------------------------------------


def test_hearing_constructs_with_valid_data() -> None:
    """should round-trip a fully-populated Hearing"""
    h = Hearing(
        title="Data Privacy Oversight Hearing",
        committee="Senate Commerce Committee",
        chamber="Senate",
        date=dt.date(2025, 3, 12),
        citation="S. Hrg. 119-42",
        url="https://example.gov/hearing/42",
    )
    assert h.title == "Data Privacy Oversight Hearing"
    assert h.committee == "Senate Commerce Committee"
    assert h.chamber == "Senate"
    assert h.date == dt.date(2025, 3, 12)
    assert h.citation == "S. Hrg. 119-42"
    assert h.url == "https://example.gov/hearing/42"


def test_hearing_optional_fields_default_none() -> None:
    """should default all optional fields to None when only title is given"""
    h = Hearing(title="Minimal Hearing")
    assert h.committee is None
    assert h.chamber is None
    assert h.date is None
    assert h.citation is None
    assert h.url is None


def test_hearing_requires_title() -> None:
    """should raise ValidationError when title is omitted"""
    with pytest.raises(ValidationError):
        Hearing.model_validate({})


# ---------------------------------------------------------------------------
# Statement
# ---------------------------------------------------------------------------


def test_statement_constructs_with_valid_data() -> None:
    """should round-trip a fully-populated Statement"""
    s = Statement(
        speaker="Sen. Jane Doe",
        role="sponsor",
        date=dt.date(2025, 4, 1),
        quote="This bill protects consumers.",
        context="Floor speech during debate",
        source_url="https://congress.gov/crec/2025/04/01",
        source_type="CREC",
        verified=True,
    )
    assert s.speaker == "Sen. Jane Doe"
    assert s.role == "sponsor"
    assert s.date == dt.date(2025, 4, 1)
    assert s.quote == "This bill protects consumers."
    assert s.context == "Floor speech during debate"
    assert s.source_url == "https://congress.gov/crec/2025/04/01"
    assert s.source_type == "CREC"
    assert s.verified is True


def test_statement_defaults_verified_false() -> None:
    """should default verified to False when not supplied"""
    s = Statement(
        speaker="Rep. John Smith",
        role="member",
        quote="I support this measure.",
        source_url="https://example.gov/press",
        source_type="press",
    )
    assert s.verified is False
    assert s.date is None
    assert s.context is None


def test_statement_invalid_role_raises_validation_error() -> None:
    """should reject an unrecognised role value"""
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {
                "speaker": "Rep. X",
                "role": "lobbyist",
                "quote": "This is a good and necessary bill for consumers.",
                "source_url": "https://example.gov",
                "source_type": "press",
            }
        )


def test_statement_invalid_source_type_raises_validation_error() -> None:
    """should reject an unrecognised source_type value"""
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {
                "speaker": "Rep. X",
                "role": "member",
                "quote": "This is a good and necessary bill for consumers.",
                "source_url": "https://example.gov",
                "source_type": "tweet",
            }
        )


def test_statement_requires_speaker() -> None:
    """should raise ValidationError when speaker is omitted"""
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {
                "role": "member",
                "quote": "This is a good and necessary bill for consumers.",
                "source_url": "https://example.gov",
                "source_type": "press",
            }
        )


def test_statement_requires_quote() -> None:
    """should raise ValidationError when quote is omitted"""
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {
                "speaker": "Rep. X",
                "role": "member",
                "source_url": "https://example.gov",
                "source_type": "press",
            }
        )


def test_statement_requires_source_url() -> None:
    """should raise ValidationError when source_url is omitted"""
    with pytest.raises(ValidationError):
        Statement.model_validate(
            {
                "speaker": "Rep. X",
                "role": "member",
                "quote": "This is a good and necessary bill for consumers.",
                "source_type": "press",
            }
        )


# ---------------------------------------------------------------------------
# LegHistory extensions
# ---------------------------------------------------------------------------


def test_leghistory_accepts_hearings_statements_narrative() -> None:
    """should store hearings, statements, and narrative alongside existing fields"""
    h = Hearing(title="Oversight Hearing")
    s = Statement(
        speaker="Rep. A",
        role="cosponsor",
        quote="We need this legislation to protect our citizens.",
        source_url="https://example.gov",
        source_type="news",
    )
    lh = LegHistory(
        hearings=[h],
        statements=[s],
        narrative="This bill originated in response to the 2024 data breach.",
    )
    assert lh.hearings == [h]
    assert lh.statements == [s]
    assert lh.narrative == "This bill originated in response to the 2024 data breach."


def test_leghistory_new_fields_default_empty_or_none() -> None:
    """should default hearings/statements to [] and narrative to None"""
    lh = LegHistory()
    assert lh.hearings == []
    assert lh.statements == []
    assert lh.narrative is None


def test_leghistory_list_defaults_are_not_shared() -> None:
    """should give each LegHistory instance its own hearings/statements lists"""
    a = LegHistory()
    b = LegHistory()
    a.hearings.append(Hearing(title="H1"))
    assert b.hearings == []
    a.statements.append(
        Statement(
            speaker="X",
            role="other",
            quote="This quote is long enough to pass the floor.",
            source_url="https://example.gov",
            source_type="other",
        )
    )
    assert b.statements == []


# ---------------------------------------------------------------------------
# Enactment extension
# ---------------------------------------------------------------------------


def test_enactment_accepts_url() -> None:
    """should store a url pointing to the public-law document"""
    from zwiadbrain.models import StatutesAtLarge
    e = Enactment(
        date_signed=dt.date(2025, 12, 1),
        public_law="119-42",
        statutes_at_large=StatutesAtLarge(citation="139 Stat. 100", url="https://www.govinfo.gov/app/details/STATUTE-139-Pg100"),
        url="https://govinfo.gov/link/plaw/119/public/42",
    )
    assert e.url == "https://govinfo.gov/link/plaw/119/public/42"


def test_enactment_url_defaults_none() -> None:
    """should default url to None when not supplied"""
    e = Enactment()
    assert e.url is None


# ---------------------------------------------------------------------------
# Phase 06: Refresh cursors and flip audit
# ---------------------------------------------------------------------------


def test_amendment_carries_latest_action_date() -> None:
    """should accept and round-trip a latest_action_date field"""
    import datetime as dt

    from zwiadbrain.models import Amendment
    a = Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 5, 1))
    assert a.latest_action_date == dt.date(2026, 5, 1)
    # default is None
    assert Amendment(number="H.Amdt. 2").latest_action_date is None


def test_bill_carries_split_cursors_and_amendments_count() -> None:
    """should carry update_date (bare), update_date_text (text-incl), summary_hash, amend_count"""
    from zwiadbrain.models import Bill
    b = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="deadbeef",
        amendments_count=3,
    )
    assert b.update_date == "2026-05-01T00:00:00Z"
    assert b.update_date_text == "2026-05-02T00:00:00Z"
    assert b.summary_hash == "deadbeef"
    assert b.amendments_count == 3
    # defaults are None / 0
    b2 = Bill(id="118-hr-2", jurisdiction="US", title="y", bill_number="H.R. 2")
    assert b2.update_date_text is None
    assert b2.summary_hash is None
    assert b2.amendments_count == 0


def test_flipout_audit_model() -> None:
    """should record a date and reason for a classifier flip-out"""
    import datetime as dt

    from zwiadbrain.models import FlipOutAudit
    f = FlipOutAudit(date=dt.date(2026, 6, 4), reason="classifier: telehealth scope drift")
    assert f.date == dt.date(2026, 6, 4)
    assert f.reason == "classifier: telehealth scope drift"


def test_bill_carries_flipped_out_audit() -> None:
    """should accept a FlipOutAudit on Bill.flipped_out (default None)"""
    import datetime as dt

    from zwiadbrain.models import Bill, FlipOutAudit
    b = Bill(
        id="118-hr-3",
        jurisdiction="US",
        title="z",
        bill_number="H.R. 3",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="r"),
    )
    assert b.flipped_out is not None
    assert b.flipped_out.reason == "r"
    b2 = Bill(id="118-hr-4", jurisdiction="US", title="q", bill_number="H.R. 4")
    assert b2.flipped_out is None


def test_statutes_at_large_is_a_typed_model() -> None:
    """should be a model with citation + url, not a bare string"""
    from zwiadbrain.models import StatutesAtLarge
    s = StatutesAtLarge(citation="138 Stat. 1234", url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1234")
    assert s.citation == "138 Stat. 1234"
    assert str(s.url).startswith("https://")


def test_enactment_statutes_at_large_uses_new_model() -> None:
    """Enactment.statutes_at_large should accept StatutesAtLarge | None"""
    from zwiadbrain.models import Enactment, StatutesAtLarge
    e = Enactment(
        statutes_at_large=StatutesAtLarge(citation="138 Stat. 1234", url="https://example.test"),
    )
    assert e.statutes_at_large is not None
    assert e.statutes_at_large.citation == "138 Stat. 1234"
    assert Enactment().statutes_at_large is None


# ---------------------------------------------------------------------------
# B44: federal Bill.id shape enforcement
# ---------------------------------------------------------------------------


def test_bill_rejects_malformed_federal_id() -> None:
    """should raise ValidationError when a US federal bill id is not <congress>-<type>-<number>"""
    with pytest.raises(ValidationError):
        Bill(id="118-hr", jurisdiction="US", title="t", bill_number="H.R. 1")


def test_bill_accepts_well_formed_federal_id() -> None:
    """should accept a valid three-segment federal id"""
    b = Bill(id="118-hjres-45", jurisdiction="US", title="t", bill_number="H.J.Res. 45")
    assert b.id == "118-hjres-45"


def test_bill_does_not_constrain_state_id_shape() -> None:
    """should leave non-US (state) ids alone — they do not use the federal triple form"""
    b = Bill(id="us-ca-sb-362", jurisdiction="US-CA", title="t", bill_number="SB 362")
    assert b.id == "us-ca-sb-362"


# ---------------------------------------------------------------------------
# B46: non-empty invariants on reason, citation, and quote floor
# ---------------------------------------------------------------------------


def test_flipout_audit_rejects_empty_reason() -> None:
    """should reject an empty FlipOutAudit.reason"""
    import datetime as dt

    from zwiadbrain.models import FlipOutAudit
    with pytest.raises(ValidationError):
        FlipOutAudit(date=dt.date(2026, 6, 4), reason="")


def test_statutes_at_large_rejects_empty_citation() -> None:
    """should reject an empty StatutesAtLarge.citation"""
    from zwiadbrain.models import StatutesAtLarge
    with pytest.raises(ValidationError):
        StatutesAtLarge(citation="", url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1")


def test_statement_rejects_quote_shorter_than_grounding_floor() -> None:
    """should reject a quote shorter than the 20-char D36 grounding floor"""
    with pytest.raises(ValidationError):
        Statement(
            speaker="Rep. X",
            role="member",
            quote="too short",
            source_url="https://example.gov",
            source_type="press",
        )


# ---------------------------------------------------------------------------
# B47: require http(s) scheme on Statement.source_url and StatutesAtLarge.url
# ---------------------------------------------------------------------------


def test_statement_rejects_non_http_source_url() -> None:
    """should reject a source_url without an http(s) scheme"""
    with pytest.raises(ValidationError):
        Statement(
            speaker="Rep. X",
            role="member",
            quote="This is a sufficiently long and groundable quote.",
            source_url="not-a-url",
            source_type="press",
        )


def test_statement_source_url_round_trips_byte_identical() -> None:
    """should keep a valid http url as a plain str with no reformatting"""
    s = Statement(
        speaker="Rep. X",
        role="member",
        quote="This is a sufficiently long and groundable quote.",
        source_url="https://congress.gov/crec/2025/04/01",
        source_type="CREC",
    )
    assert s.source_url == "https://congress.gov/crec/2025/04/01"
    assert s.model_dump()["source_url"] == "https://congress.gov/crec/2025/04/01"


def test_statutes_at_large_rejects_non_http_url() -> None:
    """should reject a StatutesAtLarge.url without an http(s) scheme"""
    from zwiadbrain.models import StatutesAtLarge
    with pytest.raises(ValidationError):
        StatutesAtLarge(citation="138 Stat. 1234", url="govinfo.gov/STATUTE")
