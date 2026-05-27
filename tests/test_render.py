"""Tests for page rendering: model -> Markdown page, path routing, idempotent writes."""

import datetime as dt
from pathlib import Path

from zwiadbrain.models import (
    Action,
    Amendment,
    Bill,
    CommentarySource,
    EnforcementAction,
)
from zwiadbrain.pipeline.render import page_path, render_page, write_page
from zwiadbrain.wiki.schema import from_page


def _bill() -> Bill:
    return Bill(
        id="us-ca-sb-362",
        jurisdiction="US-CA",
        title="California Delete Act",
        bill_number="SB 362",
        status="enrolled",
        introduced_date=dt.date(2023, 2, 10),
        summary="Creates a one-stop deletion mechanism for data brokers.",
        actions=[Action(text="Introduced", date=dt.date(2023, 2, 10), chamber="Senate")],
        amendments=[Amendment(number="A1", what_changed="Narrowed broker definition.")],
        sources={"LegiScan": "https://legiscan.com/CA/bill/SB362"},
    )


def test_render_page_includes_frontmatter_and_required_sections() -> None:
    """should emit a frontmatter block plus the standard bill body sections"""
    page = render_page(_bill())
    assert page.startswith("---")
    assert "California Delete Act" in page
    assert "## Summary" in page
    assert "## Status & Timeline" in page
    assert "## Amendments" in page
    assert "## Sources" in page


def test_render_page_frontmatter_round_trips_to_model() -> None:
    """should produce frontmatter that parses back into the same kind of model"""
    item = from_page(render_page(_bill()))
    assert isinstance(item, Bill)
    assert item.bill_number == "SB 362"


def test_render_page_omits_empty_sections() -> None:
    """should not emit headers for sections with no content"""
    page = render_page(Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1"))
    assert "## Status & Timeline" not in page
    assert "## Commentary & Analysis" not in page


def test_render_page_is_deterministic() -> None:
    """should render the same model to identical bytes (idempotency)"""
    bill = _bill()
    assert render_page(bill) == render_page(bill)


def test_commentary_section_demotes_headings_and_fences_with_markers() -> None:
    """should fence each copied page with begin/end markers and demote its headings"""
    bill = _bill()
    bill.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-california-delete-act.md",
            slug="regulation-california-delete-act",
            updated=dt.date(2026, 5, 6),
            content_hash="h",
            matched_by="deterministic",
            confidence=1.0,
            body="## Summary\n\nThe Delete Act created DROP.",
        )
    ]
    page = render_page(bill)
    assert "## Commentary & Analysis" in page
    assert "<!-- lawbrain:begin slug=regulation-california-delete-act -->" in page
    assert "<!-- lawbrain:end slug=regulation-california-delete-act -->" in page
    assert "### Summary" in page  # the copied body's ## heading is demoted to ###


def test_page_path_routes_by_jurisdiction_and_type(tmp_path: Path) -> None:
    """should route to federal/state and bills/enforcement directories by id"""
    assert page_path(_bill(), tmp_path) == tmp_path / "states" / "ca" / "bills" / "us-ca-sb-362.md"
    fed = Bill(id="hr-1", jurisdiction="US", title="t", bill_number="HR 1")
    assert page_path(fed, tmp_path) == tmp_path / "federal" / "bills" / "hr-1.md"
    enf = EnforcementAction(id="ftc-x", jurisdiction="US", title="t", agency="FTC")
    assert page_path(enf, tmp_path) == tmp_path / "federal" / "enforcement" / "ftc-x.md"


def test_write_page_is_idempotent(tmp_path: Path) -> None:
    """should write on first call, skip the rewrite when content is unchanged"""
    bill = _bill()
    assert write_page(bill, tmp_path) is True
    assert write_page(bill, tmp_path) is False
    path = page_path(bill, tmp_path)
    assert path.read_text(encoding="utf-8") == render_page(bill)
