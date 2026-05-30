"""Tests for lawbrain_copy.build_commentary_source and merge_commentary."""
import datetime as dt

from zwiadbrain.models import CommentaryLink, CommentarySource
from zwiadbrain.pipeline.lawbrain_copy import (
    build_commentary_source,
    merge_commentary,
)
from zwiadbrain.sources.lawbrain import LawBrainPage


def _page(
    slug: str = "regulation-california-sb53-tfaia",
    *,
    body: str = "## Summary\n\nThe TFAIA frontier-model law.\n",
    content_hash: str = "h0",
    updated: dt.date | None = dt.date(2025, 9, 1),
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type="regulation",
        jurisdiction=["US-CA"],
        tags=["ai", "frontier-models"],
        title="California SB 53 (TFAIA)",
        citation="Cal. SB 53",
        updated=updated,
        body=body,
        content_hash=content_hash,
        source_files=["sources/zwiad/sb53.md"],
    )


def test_build_commentary_source_copies_body_verbatim_and_carries_bookkeeping() -> None:
    page = _page()
    links = [CommentaryLink(text="IAPP analysis", url="https://iapp.org/news/a")]

    src = build_commentary_source(
        page=page, matched_by="deterministic", confidence=1.0, links=links
    )

    assert isinstance(src, CommentarySource)
    assert src.body == "## Summary\n\nThe TFAIA frontier-model law.\n"  # raw, untransformed
    assert src.slug == "regulation-california-sb53-tfaia"
    assert src.path == "regulation-california-sb53-tfaia"
    assert src.content_hash == "h0"
    assert src.updated == dt.date(2025, 9, 1)
    assert src.matched_by == "deterministic"
    assert src.confidence == 1.0
    assert src.links == links


def test_build_commentary_source_llm_matched_by() -> None:
    src = build_commentary_source(
        page=_page(), matched_by="llm", confidence=0.85, links=[]
    )
    assert src.matched_by == "llm"
    assert src.confidence == 0.85


def test_build_commentary_source_none_updated() -> None:
    src = build_commentary_source(
        page=_page(updated=None), matched_by="deterministic", confidence=1.0, links=[]
    )
    assert src.updated is None


def test_merge_commentary_first_apply_appends() -> None:
    src = build_commentary_source(
        page=_page(), matched_by="deterministic", confidence=1.0, links=[]
    )

    merged = merge_commentary([], src)

    assert [s.slug for s in merged] == ["regulation-california-sb53-tfaia"]
    assert merged[0].content_hash == "h0"


def test_merge_commentary_same_hash_reapply_is_noop_identity() -> None:
    src = build_commentary_source(
        page=_page(), matched_by="deterministic", confidence=1.0, links=[]
    )
    existing = merge_commentary([], src)

    # Re-seeing the same slug at the same content_hash returns the SAME list object
    # (identity), guaranteeing a byte-identical render and clean git status (D20).
    again = build_commentary_source(
        page=_page(content_hash="h0"), matched_by="deterministic", confidence=1.0, links=[]
    )
    assert merge_commentary(existing, again) is existing


def test_merge_commentary_changed_hash_replaces_only_that_block() -> None:
    a0 = build_commentary_source(
        page=_page(slug="regulation-a", content_hash="a0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    b0 = build_commentary_source(
        page=_page(slug="regulation-b", content_hash="b0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    existing = merge_commentary(merge_commentary([], a0), b0)

    a1 = build_commentary_source(
        page=_page(slug="regulation-a", body="## Summary\n\nAmended.\n", content_hash="a1"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    merged = merge_commentary(existing, a1)

    assert {s.slug: s.content_hash for s in merged} == {
        "regulation-a": "a1",  # replaced
        "regulation-b": "b0",  # untouched
    }
    assert next(s for s in merged if s.slug == "regulation-a").body == "## Summary\n\nAmended.\n"


def test_merge_commentary_new_slug_appends_and_sorts_by_slug() -> None:
    z = build_commentary_source(
        page=_page(slug="regulation-zebra", content_hash="z0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    a = build_commentary_source(
        page=_page(slug="regulation-alpha", content_hash="a0"),
        matched_by="llm", confidence=0.9, links=[],
    )
    merged = merge_commentary(merge_commentary([], z), a)

    assert [s.slug for s in merged] == ["regulation-alpha", "regulation-zebra"]


def test_merge_commentary_multi_source_always_slug_sorted() -> None:
    """Three sources merged in reverse order still come out slug-sorted."""
    c = build_commentary_source(
        page=_page(slug="regulation-c", content_hash="c0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    b = build_commentary_source(
        page=_page(slug="regulation-b", content_hash="b0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    a = build_commentary_source(
        page=_page(slug="regulation-a", content_hash="a0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    merged = merge_commentary(merge_commentary(merge_commentary([], c), b), a)
    assert [s.slug for s in merged] == ["regulation-a", "regulation-b", "regulation-c"]


def test_merge_commentary_replace_preserves_other_sources_unchanged() -> None:
    """When content_hash changes, the *other* source objects are the same instances."""
    a0 = build_commentary_source(
        page=_page(slug="regulation-a", content_hash="a0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    b0 = build_commentary_source(
        page=_page(slug="regulation-b", content_hash="b0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    existing = merge_commentary(merge_commentary([], a0), b0)
    b_object = next(s for s in existing if s.slug == "regulation-b")

    a1 = build_commentary_source(
        page=_page(slug="regulation-a", content_hash="a1"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    merged = merge_commentary(existing, a1)
    b_after = next(s for s in merged if s.slug == "regulation-b")

    # The untouched entry is the same object — no unnecessary copying.
    assert b_after is b_object
