"""Tests for wiki frontmatter (de)serialization and validation.

The committed page is YAML frontmatter (metadata = source of truth) plus a
rendered Markdown body. ``to_frontmatter`` emits only metadata; body content
(summary prose, timeline, amendments, copied commentary text) is rendered into
the body and never stored in frontmatter.

``leg_history.hearings`` and ``leg_history.statements`` (the researched,
verified artifacts) persist to frontmatter. The deterministic spine
(versions, committee_reports, floor_consideration, votes, conference,
enactment) and narrative remain body-only and are never serialized.
"""

import datetime as dt

import frontmatter
import pytest

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import (
    Action,
    Bill,
    CommentarySource,
    Enactment,
    Hearing,
    LegHistory,
    Statement,
    TextVersion,
    Vote,
)
from zwiadbrain.pipeline.render import render_page
from zwiadbrain.wiki.schema import from_page, to_frontmatter


def _sample_bill() -> Bill:
    return Bill(
        id="us-ca-sb-362",
        jurisdiction="US-CA",
        title="California Delete Act",
        bill_number="SB 362",
        status="enrolled",
        introduced_date=dt.date(2023, 2, 10),
        summary="Plain-language summary prose.",
        actions=[Action(text="Introduced in Senate", date=dt.date(2023, 2, 10))],
        commentary_sources=[
            CommentarySource(
                path="wiki/regulation-california-delete-act.md",
                slug="regulation-california-delete-act",
                content_hash="abc123",
                matched_by="deterministic",
                confidence=1.0,
                body="Verbatim copied commentary body.",
            )
        ],
    )


def test_to_frontmatter_excludes_body_only_fields() -> None:
    """should keep metadata in frontmatter but not rendered body content"""
    fm = to_frontmatter(_sample_bill())
    assert fm["bill_number"] == "SB 362"
    assert "summary" not in fm
    assert "actions" not in fm


def test_to_frontmatter_serializes_dates_as_iso_strings() -> None:
    """should render dates as ISO strings, not date objects"""
    fm = to_frontmatter(_sample_bill())
    assert fm["introduced_date"] == "2023-02-10"


def test_to_frontmatter_keeps_commentary_bookkeeping_but_drops_body() -> None:
    """should record commentary-source metadata without the copied body text"""
    fm = to_frontmatter(_sample_bill())
    sources = fm["commentary_sources"]
    assert isinstance(sources, list)
    assert sources[0]["slug"] == "regulation-california-delete-act"
    assert "body" not in sources[0]


def test_to_frontmatter_drops_none_and_empty_values() -> None:
    """should omit None fields and empty collections for clean, stable frontmatter"""
    fm = to_frontmatter(_sample_bill())
    assert all(value not in (None, [], {}) for value in fm.values())
    assert "public_law" not in fm  # None on this bill


def test_from_page_parses_metadata_into_model() -> None:
    """should reconstruct a Bill from a page's frontmatter"""
    post = frontmatter.Post("body")
    post.metadata = to_frontmatter(_sample_bill())
    item = from_page(frontmatter.dumps(post))
    assert isinstance(item, Bill)
    assert item.bill_number == "SB 362"
    assert item.introduced_date == dt.date(2023, 2, 10)


def test_from_page_raises_on_missing_required_field() -> None:
    """should raise WikiSchemaError when required frontmatter is missing"""
    text = "---\ntype: bill\nid: x\njurisdiction: US-CA\n---\nbody"
    with pytest.raises(WikiSchemaError):
        from_page(text)


# ---------------------------------------------------------------------------
# leg_history frontmatter persistence tests
# ---------------------------------------------------------------------------

_SPINE_FIELDS = {
    "versions",
    "committee_reports",
    "floor_consideration",
    "votes",
    "conference",
    "enactment",
    "narrative",
}


def _bill_with_full_leg_history() -> Bill:
    """Bill with a full LegHistory: spine fields + one Hearing + one Statement."""
    return Bill(
        id="us-hr-1-119",
        jurisdiction="US",
        title="Test Act",
        bill_number="HR 1",
        leg_history=LegHistory(
            versions=[TextVersion(code="IH", date=dt.date(2025, 1, 3))],
            votes=[Vote(chamber="House", result="Passed", date=dt.date(2025, 3, 1))],
            enactment=Enactment(
                date_signed=dt.date(2025, 6, 1),
                public_law="119-1",
            ),
            narrative="This bill passed swiftly.",
            hearings=[
                Hearing(
                    title="Hearing on HR 1",
                    committee="House Judiciary",
                    chamber="House",
                    date=dt.date(2025, 2, 10),
                    citation="H. Hrg. 119-5",
                    url="https://example.com/hearing",
                )
            ],
            statements=[
                Statement(
                    speaker="Rep. Jane Smith",
                    role="sponsor",
                    date=dt.date(2025, 2, 10),
                    quote="This bill will protect consumers.",
                    source_url="https://example.com/crec",
                    source_type="CREC",
                    verified=True,
                )
            ],
        ),
    )


def test_leg_history_hearings_and_statements_appear_in_frontmatter() -> None:
    """should include hearings and statements in frontmatter when present"""
    fm = to_frontmatter(_bill_with_full_leg_history())
    assert "leg_history" in fm
    lh = fm["leg_history"]
    assert isinstance(lh, dict)
    assert "hearings" in lh
    assert "statements" in lh
    assert len(lh["hearings"]) == 1  # type: ignore[arg-type]
    assert len(lh["statements"]) == 1  # type: ignore[arg-type]


def test_leg_history_spine_and_narrative_excluded_from_frontmatter() -> None:
    """should not include spine fields or narrative in frontmatter leg_history"""
    fm = to_frontmatter(_bill_with_full_leg_history())
    assert "leg_history" in fm
    lh = fm["leg_history"]
    assert isinstance(lh, dict)
    for spine_field in _SPINE_FIELDS:
        assert spine_field not in lh, f"spine field {spine_field!r} leaked into frontmatter"


def test_statement_verified_flag_preserved_in_frontmatter() -> None:
    """should retain verified=True on a statement serialized to frontmatter"""
    fm = to_frontmatter(_bill_with_full_leg_history())
    stmt = fm["leg_history"]["statements"][0]  # type: ignore[index]
    assert stmt["verified"] is True
    assert stmt["source_url"] == "https://example.com/crec"
    assert "quote" in stmt
    assert "speaker" in stmt


def test_leg_history_spine_only_emits_no_leg_history_key() -> None:
    """should omit leg_history from frontmatter when hearings and statements are empty"""
    bill = Bill(
        id="us-hr-2-119",
        jurisdiction="US",
        title="Spine Only Act",
        bill_number="HR 2",
        leg_history=LegHistory(
            versions=[TextVersion(code="IH", date=dt.date(2025, 1, 3))],
            votes=[Vote(chamber="House", result="Passed")],
            enactment=Enactment(public_law="119-2"),
            narrative="Passed quickly.",
            # no hearings, no statements
        ),
    )
    fm = to_frontmatter(bill)
    assert "leg_history" not in fm


def test_leg_history_none_emits_no_leg_history_key() -> None:
    """should omit leg_history from frontmatter when leg_history is None"""
    bill = Bill(
        id="us-hr-3-119",
        jurisdiction="US",
        title="No History Act",
        bill_number="HR 3",
        leg_history=None,
    )
    fm = to_frontmatter(bill)
    assert "leg_history" not in fm


def test_leg_history_round_trip_via_render_page() -> None:
    """should round-trip hearings/statements through render_page -> from_page, verified preserved"""
    original = _bill_with_full_leg_history()
    page_text = render_page(original)
    parsed = from_page(page_text)
    assert isinstance(parsed, Bill)
    assert parsed.leg_history is not None
    # hearings survive
    assert len(parsed.leg_history.hearings) == 1
    assert parsed.leg_history.hearings[0].title == "Hearing on HR 1"
    # statements survive with verified flag
    assert len(parsed.leg_history.statements) == 1
    stmt = parsed.leg_history.statements[0]
    assert stmt.verified is True
    assert stmt.speaker == "Rep. Jane Smith"
    # spine is empty / None (not persisted to frontmatter, not re-derived in body)
    assert parsed.leg_history.versions == []
    assert parsed.leg_history.votes == []
    assert parsed.leg_history.enactment is None
    assert parsed.leg_history.narrative is None
