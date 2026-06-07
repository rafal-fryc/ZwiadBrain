"""Sidecar path + extracted-text page region (PHASE-12).

The extracted text is saved as a ``<id>.text.md`` sibling of the page. The page
gains a marker-delimited "Extracted Text" region linking that sidecar; the region
is written on raw page text (no frontmatter round-trip) so it is byte-stable, sits
strictly last, survives a non-extract re-render (refresh), and never disturbs a
committed law-brain region.
"""

from pathlib import Path

from zwiadbrain.models import Bill, CommentaryLink, CommentarySource
from zwiadbrain.pipeline.render import (
    page_path,
    sidecar_path,
    write_extracted_text_region,
    write_page,
)
from zwiadbrain.wiki.templates import (
    EXTRACTED_TEXT_REGION_BEGIN,
    EXTRACTED_TEXT_REGION_END,
    LAWBRAIN_REGION_BEGIN,
    preserve_extracted_text_region,
    render_extracted_text_region,
)


def _bill(jurisdiction: str = "US", bill_id: str = "119-hr-1") -> Bill:
    return Bill(
        id=bill_id,
        jurisdiction=jurisdiction,
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
    )


def test_sidecar_path_is_text_md_sibling_of_page() -> None:
    bill = _bill()
    wiki = Path("wiki")
    assert page_path(bill, wiki) == wiki / "federal" / "bills" / "119-hr-1.md"
    assert sidecar_path(bill, wiki) == wiki / "federal" / "bills" / "119-hr-1.text.md"


def test_sidecar_path_for_state_bill() -> None:
    bill = _bill(jurisdiction="US-CA", bill_id="ca-2025-sb-53")
    wiki = Path("wiki")
    assert sidecar_path(bill, wiki) == wiki / "states" / "ca" / "bills" / "ca-2025-sb-53.text.md"


def test_render_region_has_markers_and_relative_link() -> None:
    region = render_extracted_text_region("119-hr-1.text.md")
    assert region.startswith(EXTRACTED_TEXT_REGION_BEGIN)
    assert region.endswith(EXTRACTED_TEXT_REGION_END)
    assert "## Extracted Text" in region
    assert "(119-hr-1.text.md)" in region


def test_preserve_appends_prev_region_when_fresh_lacks_it() -> None:
    region = render_extracted_text_region("119-hr-1.text.md")
    prev = f"---\ntitle: A\n---\n\n## Summary\n\nOld.\n\n{region}\n"
    fresh = "---\ntitle: A\n---\n\n## Summary\n\nNew.\n"
    result = preserve_extracted_text_region(prev, fresh)
    assert result == fresh.rstrip("\n") + "\n\n" + region + "\n"


def test_preserve_leaves_fresh_unchanged_when_it_has_region() -> None:
    region = render_extracted_text_region("119-hr-1.text.md")
    prev = f"---\ntitle: A\n---\n\n## Summary\n\nOld.\n\n{region}\n"
    fresh = f"---\ntitle: A\n---\n\n## Summary\n\nNew.\n\n{region}\n"
    assert preserve_extracted_text_region(prev, fresh) == fresh


def test_write_region_adds_link_and_is_idempotent(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    bill = _bill()
    assert write_page(bill, wiki) is True

    assert write_extracted_text_region(bill, wiki) is True
    page = page_path(bill, wiki).read_text(encoding="utf-8")
    assert EXTRACTED_TEXT_REGION_BEGIN in page
    assert "(119-hr-1.text.md)" in page
    assert "A summary." in page  # body preserved

    # second call writes nothing (byte-identical)
    assert write_extracted_text_region(bill, wiki) is False


def test_write_region_after_rerender_is_noop(tmp_path: Path) -> None:
    # The D20 invariant: once the region is committed, a plain re-render of the
    # same model must preserve it and write nothing.
    wiki = tmp_path / "wiki"
    bill = _bill()
    write_page(bill, wiki)
    write_extracted_text_region(bill, wiki)
    assert write_page(bill, wiki) is False


def _commentary_bill() -> Bill:
    bill = _bill()
    bill.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-x.md",
            slug="x-rule",
            content_hash="h1",
            matched_by="deterministic",
            confidence=1.0,
            body="## Analysis\n\nCommentary body.",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
        )
    ]
    return bill


def test_extracted_region_coexists_with_lawbrain_region(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    bill = _commentary_bill()
    assert write_page(bill, wiki) is True  # writes lawbrain region
    assert write_extracted_text_region(bill, wiki) is True
    page = page_path(bill, wiki).read_text(encoding="utf-8")
    assert LAWBRAIN_REGION_BEGIN in page
    assert EXTRACTED_TEXT_REGION_BEGIN in page
    assert "Commentary body." in page
    # extracted-text region sits strictly last (after the law-brain region)
    assert page.index(LAWBRAIN_REGION_BEGIN) < page.index(EXTRACTED_TEXT_REGION_BEGIN)
    # a plain re-render preserves BOTH regions and writes nothing
    assert write_page(bill, wiki) is False
