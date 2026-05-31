"""Tests for lawbrain_copy.detect_stale — staleness detection for commentary sources."""
import datetime as dt

from zwiadbrain.models import CommentarySource
from zwiadbrain.pipeline.lawbrain_copy import detect_stale


def _src(slug: str, content_hash: str = "h") -> CommentarySource:
    return CommentarySource(
        path=slug,
        slug=slug,
        updated=dt.date(2025, 9, 1),
        content_hash=content_hash,
        matched_by="deterministic",
        confidence=1.0,
        body="## Summary\n\nbody\n",
    )


def test_detect_stale_returns_existing_slugs_absent_from_live_set() -> None:
    existing = [_src("regulation-a"), _src("regulation-b"), _src("regulation-c")]
    live = {"regulation-a", "regulation-c"}

    assert detect_stale(existing, live) == ["regulation-b"]


def test_detect_stale_empty_when_all_existing_are_still_live() -> None:
    existing = [_src("regulation-a"), _src("regulation-b")]
    live = {"regulation-a", "regulation-b", "regulation-c"}

    assert detect_stale(existing, live) == []


def test_detect_stale_is_slug_sorted_and_deduped_by_existing_order() -> None:
    existing = [_src("regulation-zebra"), _src("regulation-alpha")]
    live: set[str] = set()  # both dropped from the law brain

    # Both vanished pages reported, slug-sorted for deterministic review-note output.
    assert detect_stale(existing, live) == ["regulation-alpha", "regulation-zebra"]


def test_detect_stale_all_stale_when_live_empty() -> None:
    existing = [_src("regulation-a"), _src("regulation-b")]
    assert detect_stale(existing, set()) == ["regulation-a", "regulation-b"]


def test_detect_stale_empty_existing_is_noop() -> None:
    assert detect_stale([], {"regulation-a", "regulation-b"}) == []


def test_detect_stale_returns_only_dropped_slug() -> None:
    """Only the missing slug is returned; the live one is not."""
    existing = [_src("regulation-gone"), _src("regulation-here")]
    live = {"regulation-here"}
    result = detect_stale(existing, live)
    assert result == ["regulation-gone"]
    assert "regulation-here" not in result
