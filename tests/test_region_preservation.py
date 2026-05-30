"""D63 regression guard: a non-sync re-render must not strip a committed region.

``preserve_lawbrain_region`` splices a prior page's ``lawbrain:region`` block
forward verbatim onto a freshly rendered body that lacks one, so that
``render-refreshed`` (and any other non-sync render path) keeps committed
commentary and Further Reading byte-identical.
"""

import datetime as dt
from pathlib import Path

from zwiadbrain.models import Bill, CommentaryLink, CommentarySource
from zwiadbrain.pipeline.render import page_path, render_page, write_page
from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
    preserve_lawbrain_region,
)

_REGION = (
    f"{LAWBRAIN_REGION_BEGIN}\n"
    "## Commentary & Analysis\n\n"
    "<!-- lawbrain:begin slug=x-rule -->\n"
    "> Source: law brain page `x-rule`.\n"
    "> Copied verbatim.\n\n"
    "Analysis body.\n"
    "<!-- lawbrain:end slug=x-rule -->\n\n"
    "## Further Reading (via law brain)\n\n"
    "- [Ref](https://ref.example/a)\n"
    f"{LAWBRAIN_REGION_END}"
)


def test_prev_region_spliced_onto_fresh_without_region() -> None:
    prev = f"---\ntitle: A\n---\n\n## Summary\n\nOld.\n\n## Sources\n\n- x\n\n{_REGION}\n"
    fresh = "---\ntitle: A\n---\n\n## Summary\n\nNew.\n\n## Sources\n\n- x\n"
    result = preserve_lawbrain_region(prev, fresh)
    # fresh body retained, region appended verbatim, single trailing newline
    assert result == fresh.rstrip("\n") + "\n\n" + _REGION + "\n"
    assert _REGION in result
    assert result.endswith(_REGION + "\n")


def test_prev_without_region_leaves_fresh_unchanged() -> None:
    prev = "---\ntitle: A\n---\n\n## Summary\n\nOld.\n"
    fresh = "---\ntitle: A\n---\n\n## Summary\n\nNew.\n"
    assert preserve_lawbrain_region(prev, fresh) == fresh


def test_fresh_with_region_is_authoritative() -> None:
    # a sync render produced its own region: prev region must be ignored
    prev = f"---\ntitle: A\n---\n\n## Sources\n\n- x\n\n{_REGION}\n"
    fresh_region = _REGION.replace("Analysis body.", "Updated analysis.")
    fresh = f"---\ntitle: A\n---\n\n## Sources\n\n- x\n\n{fresh_region}\n"
    assert preserve_lawbrain_region(prev, fresh) == fresh


def _commentary_bill() -> Bill:
    return Bill(
        id="119-hr-1",
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
    )


def test_write_page_preserves_region_across_body_none_refresh(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    # 1. initial sync render: bill carries a commentary source WITH a body -> region committed
    synced = _commentary_bill()
    synced.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-x.md",
            slug="x-rule",
            updated=dt.date(2026, 5, 1),
            content_hash="hash1",
            matched_by="deterministic",
            confidence=1.0,
            body="## Analysis\n\nCommentary body.",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
        )
    ]
    assert write_page(synced, wiki) is True
    committed = page_path(synced, wiki).read_text(encoding="utf-8")
    assert LAWBRAIN_REGION_BEGIN in committed

    # 2. a refresh re-render carries the SAME source as metadata-only (body=None)
    refreshed = _commentary_bill()
    refreshed.summary = "An updated summary."
    refreshed.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-x.md",
            slug="x-rule",
            updated=dt.date(2026, 5, 1),
            content_hash="hash1",
            matched_by="deterministic",
            confidence=1.0,
            body=None,
            links=[],
        )
    ]
    # render_page alone (no preservation) drops the region — proves the hazard
    assert LAWBRAIN_REGION_BEGIN not in render_page(refreshed)

    # write_page preserves it centrally
    assert write_page(refreshed, wiki) is True
    after = page_path(refreshed, wiki).read_text(encoding="utf-8")
    assert LAWBRAIN_REGION_BEGIN in after
    assert "An updated summary." in after
    assert "Commentary body." in after
