import datetime as dt

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment
from zwiadbrain.pipeline.enforcement import (
    MatterRef,
    build_shortlist,
    confirm_match,
    merge_current_state,
    merge_developments,
    respondent_overlap,
)


def test_respondent_overlap_folds_suffixes_and_punctuation() -> None:
    assert respondent_overlap("Acme, Inc.", "Acme Corporation") >= 0.5
    assert respondent_overlap("Acme Health LLC", "Acme Data Co.") < 0.5


def test_build_shortlist_filters_by_agency_overlap_and_window() -> None:
    matters = [
        MatterRef(id="ftc-2025-acme", agency_slug="ftc", jurisdiction="US",
                  respondent="Acme, Inc.", date_filed=dt.date(2025, 1, 1)),
        MatterRef(id="ftc-2025-other", agency_slug="ftc", jurisdiction="US",
                  respondent="Globex LLC", date_filed=dt.date(2025, 1, 1)),
        MatterRef(id="ca-oag-2025-acme", agency_slug="ca-oag", jurisdiction="US-CA",
                  respondent="Acme, Inc.", date_filed=dt.date(2025, 1, 1)),
    ]
    short = build_shortlist(
        agency_slug="ftc", respondent="Acme Corporation", date=dt.date(2025, 3, 1),
        matters=matters, window_days=120,
    )
    assert [m.id for m in short] == ["ftc-2025-acme"]  # same agency, overlap, in-window


def test_confirm_match_accepts_overlap_window_and_confidence() -> None:
    assert confirm_match(
        item_respondent="Acme Corporation", item_date=dt.date(2025, 3, 1),
        candidate_respondent="Acme, Inc.", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is True


def test_confirm_match_rejects_on_respondent_mismatch() -> None:
    assert confirm_match(
        item_respondent="Globex", item_date=dt.date(2025, 3, 1),
        candidate_respondent="Acme, Inc.", candidate_date=dt.date(2025, 1, 1),
        confidence=0.99, min_confidence=0.75, window_days=120,
    ) is False


def test_confirm_match_rejects_out_of_window_and_low_confidence() -> None:
    assert confirm_match(
        item_respondent="Acme", item_date=dt.date(2025, 12, 1),
        candidate_respondent="Acme", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is False
    assert confirm_match(
        item_respondent="Acme", item_date=dt.date(2025, 2, 1),
        candidate_respondent="Acme", candidate_date=dt.date(2025, 1, 1),
        confidence=0.5, min_confidence=0.75, window_days=120,
    ) is False


def test_merge_developments_dedups_by_source_url_and_sorts() -> None:
    existing = [EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="Complaint.",
                                       source_url="https://x/a")]
    same = EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="Complaint (re-seen).",
                                  source_url="https://x/a")
    new = EnforcementDevelopment(date=dt.date(2025, 6, 1), summary="Order.",
                                 source_url="https://x/b")
    assert merge_developments(existing, same) == existing
    merged = merge_developments(existing, new)
    assert [d.summary for d in merged] == ["Complaint.", "Order."]


def test_merge_current_state_is_monotonic() -> None:
    existing = EnforcementAction(id="ftc-c-1", jurisdiction="US", title="t", agency="FTC",
                                 status="filed", penalties=None)
    updated = merge_current_state(
        existing, status="settled", date_resolved=dt.date(2025, 6, 1),
        penalties="$5M", outcome="Consent order.", significance=None,
    )
    assert updated.status == "settled"
    assert updated.penalties == "$5M"
    existing2 = merge_current_state(updated, status=None, date_resolved=None,
                                    penalties=None, outcome=None, significance=None)
    assert existing2.status == "settled"
    assert existing2.penalties == "$5M"


def test_confirm_match_missing_date_requires_stronger_overlap() -> None:
    # No date proximity to lean on: overlap 0.5 ("Health Data Inc" -> {health, data}
    # vs "Health LLC" -> {health}) is below the 0.6 missing-date floor -> rejected.
    assert respondent_overlap("Health Data Inc", "Health LLC") == 0.5
    assert confirm_match(
        item_respondent="Health Data Inc", item_date=None,
        candidate_respondent="Health LLC", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is False
    # Overlap 1.0 clears the stronger floor even with a missing date -> confirmed.
    assert confirm_match(
        item_respondent="Acme, Inc.", item_date=None,
        candidate_respondent="Acme Corporation", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is True


def test_confirm_match_at_overlap_floor() -> None:
    # Just below the 0.34 floor: 1/3 ~ 0.333 -> rejected even with both dates known.
    assert respondent_overlap("Acme Health", "Acme Data") < 0.34
    assert confirm_match(
        item_respondent="Acme Health", item_date=dt.date(2025, 2, 1),
        candidate_respondent="Acme Data", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is False
    # Just above the floor: 0.4 -> confirmed.
    assert respondent_overlap("Acme Health Care", "Acme Health Data Group") >= 0.34
    assert confirm_match(
        item_respondent="Acme Health Care", item_date=dt.date(2025, 2, 1),
        candidate_respondent="Acme Health Data Group", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is True


def test_build_shortlist_empty_when_nothing_clears_floor() -> None:
    matters = [
        MatterRef(id="ca-oag-2025-acme", agency_slug="ca-oag", jurisdiction="US-CA",
                  respondent="Acme, Inc.", date_filed=dt.date(2025, 1, 1)),
        MatterRef(id="ftc-2025-globex", agency_slug="ftc", jurisdiction="US",
                  respondent="Globex LLC", date_filed=dt.date(2025, 1, 1)),
    ]
    # Wrong agency (ca-oag) is filtered; same-agency Globex shares no tokens with Acme.
    assert build_shortlist(
        agency_slug="ftc", respondent="Acme Corporation", date=dt.date(2025, 3, 1),
        matters=matters, window_days=120,
    ) == []


def test_merge_developments_tie_breaks_on_source_url() -> None:
    existing = [EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="B.",
                                       source_url="https://x/b")]
    new = EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="A.",
                                 source_url="https://x/a")
    merged = merge_developments(existing, new)
    assert [str(d.source_url) for d in merged] == ["https://x/a", "https://x/b"]


def test_respondent_overlap_zero_when_only_stopwords() -> None:
    assert respondent_overlap("Inc", "LLC") == 0.0
