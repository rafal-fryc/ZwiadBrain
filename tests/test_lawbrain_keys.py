"""Tests for jurisdiction-qualified key extraction (pipeline/lawbrain_keys.py)."""

from __future__ import annotations

import hashlib

from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.pipeline.lawbrain_keys import (
    _bill_keys_from_text,  # pyright: ignore[reportPrivateUsage]
    keys_hash,
    normalize_jurisdiction,
    page_keys,
    tracked_item_keys,
)
from zwiadbrain.sources.lawbrain import LawBrainPage

_MARKERS = ["tracker", "landscape", "map", "scholarship"]


def _page(
    *,
    slug: str,
    jurisdiction: list[str],
    title: str = "",
    citation: str | None = None,
    tags: list[str] | None = None,
    type_: str = "regulation",
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type=type_,
        jurisdiction=jurisdiction,
        tags=tags or [],
        title=title,
        citation=citation,
        updated=None,
        body="",
        content_hash="0" * 64,
        source_files=[],
    )


def test_normalize_jurisdiction_maps_us_federal_to_us() -> None:
    assert normalize_jurisdiction("US-Federal") == "US"


def test_normalize_jurisdiction_passes_through_state_codes() -> None:
    assert normalize_jurisdiction("US-CA") == "US-CA"


def test_normalize_jurisdiction_passes_through_us() -> None:
    assert normalize_jurisdiction("US") == "US"


def test_page_keys_extracts_state_bill_jurisdiction_qualified() -> None:
    page = _page(
        slug="regulation-california-sb53-tfaia",
        jurisdiction=["US-CA"],
        title="California SB 53 (TFAIA)",
    )
    assert "US-CA::bill::SB-53" in page_keys(page, _MARKERS)


def test_page_keys_normalizes_federal_bill_from_title() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US-Federal"],
        title="TAKE IT DOWN Act (H.R. 8818)",
    )
    assert "US::bill::HR-8818" in page_keys(page, _MARKERS)


def test_page_keys_extracts_docket_via_parse_strong_key() -> None:
    page = _page(
        slug="case-acme-data-breach",
        jurisdiction=["US"],
        title="United States v. Acme, Docket 2:25-cv-12295",
    )
    assert "docket::2-25-cv-12295" in page_keys(page, _MARKERS)


def test_page_keys_extracts_public_law() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US"],
        title="TAKE IT DOWN Act",
        citation="Pub. L. 119-12",
    )
    assert "public_law::119-12" in page_keys(page, _MARKERS)


def test_page_keys_fail_closed_on_scholarship_slug_marker() -> None:
    page = _page(
        slug="concept-ai-liability-scholarship",
        jurisdiction=["US-CA"],
        title="AI Liability — SB 53 discussion",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_fail_closed_on_landscape_slug_marker() -> None:
    page = _page(
        slug="concept-california-ai-regulatory-landscape",
        jurisdiction=["US-CA"],
        title="California AI Regulatory Landscape (SB 53, AB 1064)",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_fail_closed_on_tracker_slug_marker() -> None:
    page = _page(
        slug="concept-federal-ai-tracker",
        jurisdiction=["US"],
        title="Federal AI Bills Tracker (HR 1, HR 2)",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_fail_closed_on_map_slug_marker() -> None:
    page = _page(
        slug="concept-state-law-map",
        jurisdiction=["US-CA"],
        title="State AI Law Map",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_law_review_citation_yields_no_bill_key() -> None:
    page = _page(
        slug="concept-algorithmic-accountability",
        jurisdiction=["US"],
        title="Algorithmic Accountability",
        citation="103 Calif. L. Rev. 513 (2015)",
    )
    keys = page_keys(page, _MARKERS)
    assert not any(k.endswith("::bill::S-513") for k in keys)
    assert not any("::bill::" in k for k in keys)


def test_page_keys_empty_jurisdiction_yields_no_bill_keys() -> None:
    page = _page(
        slug="regulation-some-bill",
        jurisdiction=[],
        title="SB 100 — Something",
    )
    keys = page_keys(page, _MARKERS)
    assert not any("::bill::" in k for k in keys)


def test_page_keys_extracts_public_law_pl_form() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US"],
        title="TAKE IT DOWN Act",
        citation="P.L. 119-12",
    )
    assert "public_law::119-12" in page_keys(page, _MARKERS)


def test_page_keys_from_docket_only_citation() -> None:
    # Citation carries a docket but no bill number; the key must come from the
    # citation field via parse_strong_key, not from slug/title (which have none).
    page = _page(
        slug="case-acme-data-breach",
        jurisdiction=["US"],
        title="United States v. Acme",
        citation="Docket 2:25-cv-12295",
    )
    assert "docket::2-25-cv-12295" in page_keys(page, _MARKERS)


def test_page_keys_from_tags_field() -> None:
    page = _page(
        slug="regulation-federal-ai-transparency-act",  # no bill number in slug
        jurisdiction=["US-Federal"],
        title="Federal AI Transparency Act",  # no bill number in title
        tags=["H.R. 1234"],  # matches _BILL_RE directly (canonical form)
    )
    assert "US::bill::HR-1234" in page_keys(page, _MARKERS)


def test_tracked_item_keys_for_state_bill() -> None:
    bill = Bill(
        id="ca-2025-sb-53",
        jurisdiction="US-CA",
        title="SB 53",
        bill_number="SB 53",
    )
    assert tracked_item_keys(bill) == {"US-CA::bill::SB-53"}


def test_tracked_item_keys_for_federal_bill() -> None:
    bill = Bill(
        id="119-hr-8818",
        jurisdiction="US",
        title="TAKE IT DOWN Act",
        bill_number="H.R. 8818",
    )
    assert tracked_item_keys(bill) == {"US::bill::HR-8818"}


def test_tracked_item_keys_unparseable_bill_number_yields_no_keys() -> None:
    # A bill_number with no recognizable <prefix><digits> pattern -> no key
    # (the regex finds no recognized bill-type token in "Unknown 2025").
    bill = Bill(
        id="ca-2025-unknown",
        jurisdiction="US-CA",
        title="Unknown",
        bill_number="Unknown 2025",
    )
    assert tracked_item_keys(bill) == set()


def test_tracked_item_keys_for_enforcement_docket_and_public_law() -> None:
    action = EnforcementAction(
        id="ftc-2-25-cv-12295",
        jurisdiction="US",
        title="United States v. Acme",
        agency="FTC",
        docket="2:25-cv-12295",
        statutes=["Pub. L. 119-12", "15 U.S.C. 45"],
    )
    keys = tracked_item_keys(action)
    assert "docket::2-25-cv-12295" in keys
    assert "public_law::119-12" in keys


def test_tracked_item_keys_enforcement_no_docket_no_publaw() -> None:
    action = EnforcementAction(
        id="ftc-2024-acme",
        jurisdiction="US",
        title="In re Acme",
        agency="FTC",
    )
    assert tracked_item_keys(action) == set()


def test_tracked_item_keys_enforcement_statute_no_publaw() -> None:
    action = EnforcementAction(
        id="ftc-2024-acme",
        jurisdiction="US",
        title="In re Acme",
        agency="FTC",
        statutes=["15 U.S.C. 45"],
    )
    keys = tracked_item_keys(action)
    assert not any("public_law::" in k for k in keys)


def test_page_and_tracked_keys_intersect_on_shared_state_bill() -> None:
    page = _page(
        slug="regulation-california-sb53-tfaia",
        jurisdiction=["US-CA"],
        title="California SB 53 (TFAIA)",
    )
    bill = Bill(id="ca-2025-sb-53", jurisdiction="US-CA", title="SB 53", bill_number="SB 53")
    assert page_keys(page, _MARKERS) & tracked_item_keys(bill) == {"US-CA::bill::SB-53"}


def test_page_and_tracked_keys_intersect_on_public_law() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US"],
        title="TAKE IT DOWN Act",
        citation="Pub. L. 119-12",
    )
    action = EnforcementAction(
        id="ftc-2-25-cv-12295",
        jurisdiction="US",
        title="United States v. Acme",
        agency="FTC",
        docket="2:25-cv-12295",
        statutes=["Pub. L. 119-12"],
    )
    assert "public_law::119-12" in (page_keys(page, _MARKERS) & tracked_item_keys(action))


def test_keys_hash_is_order_independent_and_stable() -> None:
    a = keys_hash({"US::bill::HR-8818", "public_law::119-12"})
    b = keys_hash({"public_law::119-12", "US::bill::HR-8818"})
    assert a == b
    assert len(a) == 64
    # Empty set joins to "" -> sha256(b""); pin the concrete digest, not a
    # self-comparison (which would pass for any implementation).
    assert keys_hash(set()) == hashlib.sha256(b"").hexdigest()
    assert keys_hash({"x"}) != keys_hash({"y"})


def test_bill_keys_from_text_strips_leading_zeros() -> None:
    keys = _bill_keys_from_text("SB 0053", "US-CA")
    assert "US-CA::bill::SB-53" in keys


def test_bill_keys_from_text_handles_dotted_prefix() -> None:
    keys = _bill_keys_from_text("H.R. 8818", "US")
    assert "US::bill::HR-8818" in keys
