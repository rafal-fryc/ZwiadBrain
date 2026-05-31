"""Tests for the pure jurisdiction-scoped shortlist + shared-key grounding confirm
(pipeline/lawbrain_match.py).

Covers:
- build_shortlist jurisdiction scoping (same-juris in, other-juris out)
- build_shortlist overlap ranking (higher overlap ranks first)
- build_shortlist US-Federal -> US normalization
- build_shortlist returns empty when no jurisdiction match
- confirm_match: shared key + confidence >= min -> True
- confirm_match: no shared key + require_shared_key=True -> False
- confirm_match: override=True bypasses shared-key gate (but not confidence floor)
- confirm_match: confidence < min -> False (even with shared key and/or override)
- confirm_match: require_shared_key=False + no shared key -> True (topical pass)
"""

from __future__ import annotations

import datetime as dt

from zwiadbrain.pipeline.lawbrain_match import (
    TargetRef,
    build_shortlist,
    confirm_match,
)
from zwiadbrain.sources.lawbrain import LawBrainPage


def _page(
    *,
    slug: str = "regulation-california-sb53-tfaia",
    jurisdiction: list[str] | None = None,
    tags: list[str] | None = None,
    title: str = "California SB 53 (TFAIA)",
    citation: str | None = "SB 53",
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type="regulation",
        jurisdiction=jurisdiction if jurisdiction is not None else ["US-CA"],
        tags=tags if tags is not None else ["ai", "transparency", "sb-53"],
        title=title,
        citation=citation,
        updated=dt.date(2026, 1, 1),
        body="## Summary\n\nBody.",
        content_hash="deadbeef",
        source_files=[],
    )


# ---------------------------------------------------------------------------
# build_shortlist
# ---------------------------------------------------------------------------


def test_build_shortlist_scopes_to_normalized_jurisdiction() -> None:
    page = _page(jurisdiction=["US-CA"], tags=["ai", "sb-53"])
    targets = [
        TargetRef(
            id="ca-2025-sb-53",
            kind="bill",
            jurisdiction="US-CA",
            title="SB 53 — AI transparency",
            keys=["US-CA::bill::SB-53"],
        ),
        TargetRef(
            id="ca-2025-ab-1064",
            kind="bill",
            jurisdiction="US-CA",
            title="AB 1064 — chatbots",
            keys=["US-CA::bill::AB-1064"],
        ),
        TargetRef(
            id="118-hr-2670",
            kind="bill",
            jurisdiction="US",
            title="HR 2670 — NDAA",
            keys=["US::bill::HR-2670"],
        ),
    ]
    short = build_shortlist(page, targets)
    ids = [t.id for t in short]
    assert "118-hr-2670" not in ids  # other jurisdiction excluded entirely
    assert set(ids) == {"ca-2025-sb-53", "ca-2025-ab-1064"}


def test_build_shortlist_ranks_by_tag_keyword_overlap_desc() -> None:
    page = _page(
        jurisdiction=["US-CA"],
        tags=["sb-53", "transparency"],
        title="SB 53 transparency",
    )
    targets = [
        TargetRef(
            id="ca-2025-ab-1337",
            kind="bill",
            jurisdiction="US-CA",
            title="AB 1337 — unrelated employment topic",
            keys=["US-CA::bill::AB-1337"],
        ),
        TargetRef(
            id="ca-2025-sb-53",
            kind="bill",
            jurisdiction="US-CA",
            title="SB 53 transparency requirements",
            keys=["US-CA::bill::SB-53"],
        ),
    ]
    short = build_shortlist(page, targets)
    assert [t.id for t in short][0] == "ca-2025-sb-53"  # higher overlap ranks first


def test_build_shortlist_normalizes_us_federal_against_us_targets() -> None:
    page = _page(
        jurisdiction=["US-Federal"],
        tags=["ndaa"],
        title="NDAA FY2024",
        citation="H.R. 2670",
    )
    targets = [
        TargetRef(
            id="118-hr-2670",
            kind="bill",
            jurisdiction="US",
            title="HR 2670 — NDAA",
            keys=["US::bill::HR-2670"],
        ),
        TargetRef(
            id="ca-2025-sb-53",
            kind="bill",
            jurisdiction="US-CA",
            title="SB 53",
            keys=["US-CA::bill::SB-53"],
        ),
    ]
    short = build_shortlist(page, targets)
    assert [t.id for t in short] == ["118-hr-2670"]  # US-Federal -> US


def test_build_shortlist_empty_when_no_jurisdiction_match() -> None:
    page = _page(jurisdiction=["US-NY"])
    targets = [
        TargetRef(
            id="ca-2025-sb-53",
            kind="bill",
            jurisdiction="US-CA",
            title="SB 53",
            keys=["US-CA::bill::SB-53"],
        ),
    ]
    assert build_shortlist(page, targets) == []


# ---------------------------------------------------------------------------
# confirm_match
# ---------------------------------------------------------------------------


def test_confirm_match_links_when_confidence_and_shared_key() -> None:
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::SB-53"},
            confidence=0.9,
            min_confidence=0.75,
            require_shared_key=True,
        )
        is True
    )


def test_confirm_match_links_at_exact_confidence_floor() -> None:
    # The floor is `>=`, so confidence == min_confidence must pass (boundary).
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::SB-53"},
            confidence=0.75,
            min_confidence=0.75,
            require_shared_key=True,
        )
        is True
    )


def test_confirm_match_rejects_no_shared_key_when_required() -> None:
    # Topical LLM proposal, no identifier overlap -> falls to review (weak-grounding).
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::AB-1064"},
            confidence=0.95,
            min_confidence=0.75,
            require_shared_key=True,
        )
        is False
    )


def test_confirm_match_override_bypasses_shared_key() -> None:
    # Operator override recorded in links.yaml -> apply despite no shared key.
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::AB-1064"},
            confidence=0.8,
            min_confidence=0.75,
            require_shared_key=True,
            override=True,
        )
        is True
    )


def test_confirm_match_rejects_below_confidence_floor() -> None:
    # Confidence floor is checked first; shared key alone does not rescue it.
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::SB-53"},
            confidence=0.5,
            min_confidence=0.75,
            require_shared_key=True,
        )
        is False
    )
    # Even an override cannot bypass the confidence floor.
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::SB-53"},
            confidence=0.5,
            min_confidence=0.75,
            require_shared_key=True,
            override=True,
        )
        is False
    )


def test_confirm_match_topical_passes_when_shared_key_not_required() -> None:
    # require_shared_key=False -> confidence alone suffices (topical link allowed).
    assert (
        confirm_match(
            page_keys={"US-CA::bill::SB-53"},
            target_keys={"US-CA::bill::AB-1064"},
            confidence=0.8,
            min_confidence=0.75,
            require_shared_key=False,
        )
        is True
    )
