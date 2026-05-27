"""Tests for wiki frontmatter (de)serialization and validation.

The committed page is YAML frontmatter (metadata = source of truth) plus a
rendered Markdown body. ``to_frontmatter`` emits only metadata; body content
(summary prose, timeline, amendments, copied commentary text) is rendered into
the body and never stored in frontmatter.
"""

import datetime as dt

import frontmatter
import pytest

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import Action, Bill, CommentarySource
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
