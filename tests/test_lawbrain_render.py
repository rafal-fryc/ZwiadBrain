"""Tests for the law-brain commentary render layer (Phase 09).

Covers wikilink neutralization, Further Reading aggregation, the marker-delimited
``lawbrain:region`` (rendered last, only from sources carrying a body), and the
region-omitted case for refresh metadata that carries ``body=None``.
"""

import datetime as dt

from zwiadbrain.models import Bill, CommentaryLink, CommentarySource, EnforcementAction
from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
    _further_reading,  # pyright: ignore[reportPrivateUsage]
    _lawbrain_region,  # pyright: ignore[reportPrivateUsage]
    _neutralize_wikilinks,  # pyright: ignore[reportPrivateUsage]
    render_bill_body,
    render_enforcement_body,
)


def _bill() -> Bill:
    return Bill(
        id="119-hr-1",
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
    )


def _source(
    *,
    slug: str,
    body: str | None,
    links: list[CommentaryLink] | None = None,
    updated: dt.date | None = None,
) -> CommentarySource:
    return CommentarySource(
        path=f"wiki/regulation-{slug}.md",
        slug=slug,
        updated=updated,
        content_hash="deadbeef",
        matched_by="deterministic",
        confidence=1.0,
        body=body,
        links=links or [],
    )


def test_neutralize_wikilinks_strips_double_bracket_refs() -> None:
    text = "See [[regulation-foo]] and [[Some Other Page]] for context."
    assert _neutralize_wikilinks(text) == "See regulation-foo and Some Other Page for context."


def test_neutralize_wikilinks_leaves_markdown_links_untouched() -> None:
    text = "See [the rule](https://example.gov/rule) for details."
    assert _neutralize_wikilinks(text) == "See [the rule](https://example.gov/rule) for details."


def test_further_reading_dedups_and_sorts_by_host() -> None:
    sources = [
        _source(
            slug="b-rule",
            body="x",
            links=[
                CommentaryLink(text="Zeta analysis", url="https://zeta.example/a"),
                CommentaryLink(text="Alpha brief", url="https://alpha.example/x"),
            ],
        ),
        _source(
            slug="a-rule",
            body="y",
            links=[
                # duplicate of zeta.example/a after trailing-slash normalization
                CommentaryLink(text="Zeta (dup)", url="https://zeta.example/a/"),
                CommentaryLink(text="Beta note", url="https://beta.example/n"),
            ],
        ),
    ]
    # _further_reading sorts the sources internally by slug ("a-rule" < "b-rule"),
    # so a-rule is iterated first and wins the zeta dup despite appearing second in
    # the list above — keeping a-rule's anchor text "Zeta (dup)" but emitting the
    # canonical (slash-free) URL; rows then sorted by (host, normalized url).
    assert _further_reading(sources) == (
        "- [Alpha brief](https://alpha.example/x)\n"
        "- [Beta note](https://beta.example/n)\n"
        "- [Zeta (dup)](https://zeta.example/a)"
    )


def test_further_reading_empty_when_no_links() -> None:
    assert _further_reading([_source(slug="a", body="x")]) == ""


def test_lawbrain_region_wraps_commentary_and_further_reading_in_markers() -> None:
    sources = [
        _source(
            slug="x-rule",
            body="## Background\n\nText with [[regulation-foo]].",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
            updated=dt.date(2026, 5, 1),
        )
    ]
    region = _lawbrain_region(sources)
    assert region is not None
    assert region.startswith(LAWBRAIN_REGION_BEGIN)
    assert region.endswith(LAWBRAIN_REGION_END)
    assert "## Commentary & Analysis" in region
    assert "## Further Reading (via law brain)" in region
    assert "- [Ref](https://ref.example/a)" in region
    # heading demoted (## -> ###) and wikilink neutralized inside the block
    assert "### Background" in region
    assert "regulation-foo" in region
    assert "[[regulation-foo]]" not in region


def test_lawbrain_region_omits_further_reading_when_no_links() -> None:
    region = _lawbrain_region([_source(slug="x", body="Just prose.")])
    assert region is not None
    assert "## Commentary & Analysis" in region
    assert "## Further Reading (via law brain)" not in region


def test_lawbrain_region_none_when_empty() -> None:
    assert _lawbrain_region([]) is None


def test_render_bill_body_appends_region_after_sources() -> None:
    bill = _bill()
    bill.commentary_sources = [
        _source(
            slug="x-rule",
            body="## Analysis\n\nCommentary text.",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
        )
    ]
    body = render_bill_body(bill)
    # region present and wrapped in markers
    assert LAWBRAIN_REGION_BEGIN in body
    assert LAWBRAIN_REGION_END in body
    # region renders LAST: after the Sources section
    assert body.index("## Sources") < body.index(LAWBRAIN_REGION_BEGIN)
    # commentary is no longer an inline section header outside the region
    assert body.count("## Commentary & Analysis") == 1
    assert body.index(LAWBRAIN_REGION_BEGIN) < body.index("## Commentary & Analysis")


def test_render_bill_body_omits_region_for_body_none_source() -> None:
    bill = _bill()
    # refresh-carried metadata: body is None, so no region should render
    bill.commentary_sources = [_source(slug="x-rule", body=None)]
    body = render_bill_body(bill)
    assert LAWBRAIN_REGION_BEGIN not in body
    assert "## Commentary & Analysis" not in body


def test_render_enforcement_body_appends_region_after_sources() -> None:
    action = EnforcementAction(
        id="us-ftc-2025-acme",
        jurisdiction="US",
        agency="FTC",
        title="In re Acme",
        summary="A matter.",
        sources={"FTC": "https://www.ftc.gov/acme"},
    )
    action.commentary_sources = [_source(slug="acme-rule", body="Commentary.")]
    body = render_enforcement_body(action)
    assert LAWBRAIN_REGION_BEGIN in body
    assert body.index("## Sources") < body.index(LAWBRAIN_REGION_BEGIN)
