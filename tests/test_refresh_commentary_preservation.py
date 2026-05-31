"""Regression guard for D63: a refresh must not strip committed law-brain commentary.

`render-refreshed` re-renders a freshly-fetched bill whose `commentary_sources`
list is empty (the fetch half never touches the law brain). Two mechanisms keep
the committed commentary alive across that re-render:

1. The CLI carries `prev.commentary_sources` onto the fresh bill so the
   frontmatter bookkeeping (path/slug/content_hash/matched_by/confidence) survives.
2. `write_page` splices the committed `lawbrain:region` body block forward
   verbatim (central preservation in pipeline/render.py).

This test exercises both together end-to-end and asserts byte-identical survival
of the region and the frontmatter — the data-loss regression guard for D63.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill, CommentarySource
from zwiadbrain.pipeline.render import page_path, write_page
from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
)


def _committed_bill() -> Bill:
    """A tracked federal bill that already carries one law-brain commentary source.

    The body is present (not None) so `write_page` renders the lawbrain:region.
    """
    return Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="Bill One",
        bill_number="H.R. 1",
        type="bill",
        tracking=True,
        summary="Old summary.",
        topics=["ai"],
        commentary_sources=[
            CommentarySource(
                path="wiki/regulation-take-it-down-act.md",
                slug="regulation-take-it-down-act",
                updated=None,
                content_hash="abc123",
                matched_by="deterministic",
                confidence=1.0,
                body="## Summary\n\nThe TAKE IT DOWN Act analysis.",
            )
        ],
    )


def test_render_refreshed_preserves_committed_lawbrain_region_and_frontmatter(
    tmp_path: Path,
) -> None:
    """should keep the lawbrain:region body block and commentary_sources frontmatter
    byte-identical when a refresh re-renders a fresh bill with empty commentary_sources
    """
    # Arrange — commit a page that already carries law-brain commentary.
    wiki = tmp_path / "wiki"
    committed = _committed_bill()
    assert write_page(committed, wiki) is True
    page_file = page_path(committed, wiki)
    before = page_file.read_text(encoding="utf-8")
    # Sanity: the committed page really has a region and the demoted heading.
    assert LAWBRAIN_REGION_BEGIN in before
    assert LAWBRAIN_REGION_END in before
    assert "### Summary" in before  # ## demoted to ### inside the commentary block
    assert "regulation-take-it-down-act" in before  # frontmatter bookkeeping

    # The fresh bill from fetch-refreshable carries NO commentary (empty list).
    fresh = {
        "id": "118-hr-1",
        "jurisdiction": "US",
        "title": "Bill One",
        "bill_number": "H.R. 1",
        "type": "bill",
        "tracking": True,
        "topics": ["ai"],
        "summary": "Refreshed summary.",
    }
    prev = {
        **fresh,
        "summary": "Old summary.",
        "commentary_sources": [
            {
                "path": "wiki/regulation-take-it-down-act.md",
                "slug": "regulation-take-it-down-act",
                "updated": None,
                "content_hash": "abc123",
                "matched_by": "deterministic",
                "confidence": 1.0,
                "body": "## Summary\n\nThe TAKE IT DOWN Act analysis.",
            }
        ],
    }
    refreshed = [
        {
            "bill_id": "118-hr-1",
            "prev": prev,
            "bill": fresh,
            "classifier_in_scope": True,
            "classifier_rationale": "still about AI",
        }
    ]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")

    # Act — refresh the bill.
    result = CliRunner().invoke(
        app,
        [
            "render-refreshed",
            "--in",
            str(run / "refreshed.json"),
            "--wiki",
            str(wiki),
            "--db",
            str(tmp_path / "idx.sqlite"),
        ],
    )

    # Assert — refresh succeeded and the summary updated.
    assert result.exit_code == 0, result.output
    after = page_file.read_text(encoding="utf-8")
    assert "Refreshed summary." in after

    # The lawbrain:region body block survived byte-identical.
    region_before = before[
        before.index(LAWBRAIN_REGION_BEGIN) : before.index(LAWBRAIN_REGION_END)
        + len(LAWBRAIN_REGION_END)
    ]
    region_after = after[
        after.index(LAWBRAIN_REGION_BEGIN) : after.index(LAWBRAIN_REGION_END)
        + len(LAWBRAIN_REGION_END)
    ]
    assert region_after == region_before
    assert "### Summary" in after
    assert "The TAKE IT DOWN Act analysis." in after

    # The commentary_sources frontmatter bookkeeping survived.
    assert "regulation-take-it-down-act" in after
    assert "content_hash: abc123" in after
    assert "matched_by: deterministic" in after
