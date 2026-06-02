"""Tests for the pure refresh-detection functions in pipeline/refresh.py."""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from zwiadbrain.models import (
    Amendment,
    Bill,
    FlipOutAudit,
    Hearing,
    LegHistory,
    RelatedMedia,
    Statement,
)
from zwiadbrain.pipeline.refresh import (
    RefreshableBill,
    apply_classifier_flip,
    detect_refreshable,
    preserve_leg_history,
    summary_hash,
)


def _bill(**overrides: object) -> Bill:
    """Construct a minimal Bill for tests, accepting field overrides."""
    base: dict[str, object] = dict(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="hash-prev",
        amendments_count=0,
        amendments=[],
    )
    base.update(overrides)
    return Bill(**base)  # type: ignore[arg-type]


# --- summary_hash -----------------------------------------------------------


def test_summary_hash_normalizes_whitespace() -> None:
    """should produce identical hashes for strings that differ only in whitespace"""
    a = summary_hash("This  bill\n establishes\tan AI board.")
    b = summary_hash("This bill establishes an AI board.")
    assert a == b


def test_summary_hash_differs_on_single_char_change() -> None:
    """should change when any non-whitespace character changes"""
    a = summary_hash("This bill establishes an AI board.")
    b = summary_hash("This bill establishes an AI panel.")
    assert a != b


def test_summary_hash_returns_none_for_empty() -> None:
    """should return None for None and empty/whitespace-only inputs"""
    assert summary_hash(None) is None
    assert summary_hash("") is None
    assert summary_hash("   \n\t  ") is None


def test_summary_hash_matches_expected_sha256() -> None:
    """should be a hex sha256 of the whitespace-collapsed normalized text"""
    text = "  A B C  "
    expected = hashlib.sha256(b"A B C").hexdigest()
    assert summary_hash(text) == expected


# --- detect_refreshable -----------------------------------------------------


def test_detect_refreshable_returns_none_when_update_date_unchanged() -> None:
    """should return None when prev and fresh have the same update_date"""
    prev = _bill()
    fresh = _bill()
    assert detect_refreshable(prev, fresh) is None


def test_detect_refreshable_flags_text_change_for_classifier_and_summarizer() -> None:
    """should set needs_classifier and needs_summarizer when text-date OR summary_hash differs"""
    prev = _bill()
    fresh = _bill(
        update_date="2026-05-03T00:00:00Z",
        update_date_text="2026-05-03T00:00:00Z",
        summary_hash="hash-new",
    )
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is True
    assert result.needs_summarizer is True
    assert result.changed_amendment_numbers == ()


def test_detect_refreshable_skips_classifier_when_only_status_changed() -> None:
    """should leave needs_classifier=False when only update_date moved (not text/hash)"""
    prev = _bill()
    fresh = _bill(update_date="2026-05-03T00:00:00Z")
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is False
    assert result.needs_summarizer is False


def test_detect_refreshable_flags_new_and_advanced_amendments() -> None:
    """should return numbers for new amendments and amendments whose date advanced"""
    prev = _bill(
        amendments=[
            Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1)),
            Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 4, 5)),
        ],
        amendments_count=2,
    )
    fresh = _bill(
        update_date="2026-05-03T00:00:00Z",
        amendments=[
            Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1)),  # unchanged
            Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 5, 1)),  # advanced
            Amendment(number="H.Amdt. 3", latest_action_date=dt.date(2026, 5, 2)),  # new
        ],
        amendments_count=3,
    )
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert set(result.changed_amendment_numbers) == {"H.Amdt. 2", "H.Amdt. 3"}
    assert result.needs_explainer is True


def test_refreshable_bill_carries_prev_and_fresh() -> None:
    """RefreshableBill should expose both bills"""
    prev = _bill()
    fresh = _bill(update_date="2026-05-03T00:00:00Z")
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert isinstance(result, RefreshableBill)
    assert result.prev.update_date == "2026-05-01T00:00:00Z"
    assert result.fresh.update_date == "2026-05-03T00:00:00Z"


# --- preserve_leg_history ---------------------------------------------------


def test_preserve_leg_history_returns_spine_unchanged_when_prev_is_none() -> None:
    """should return the fresh spine as-is when prev leg_history is None"""
    fresh_spine = LegHistory(narrative=None, hearings=[], statements=[])
    out = preserve_leg_history(None, fresh_spine)
    assert out is fresh_spine or out == fresh_spine


def test_preserve_leg_history_reattaches_hearings_statements_narrative() -> None:
    """should copy hearings/statements/narrative from prev onto fresh spine"""
    from zwiadbrain.models import CommitteeReport, TextVersion
    prev = LegHistory(
        hearings=[Hearing(title="H1", url="https://example.test/h1")],
        statements=[Statement(
            speaker="Sen. Reed", role="member", quote="x" * 30,
            source_url="https://example.test/s", source_type="CREC",
        )],
        narrative="The old narrative.",
    )
    fresh = LegHistory(
        versions=[TextVersion(code="enr", date=dt.date(2026, 5, 1))],
        committee_reports=[CommitteeReport(citation="H. Rept. 1", url="https://example.test/c")],
    )
    out = preserve_leg_history(prev, fresh)
    # research carried from prev
    assert out.hearings == prev.hearings
    assert out.statements == prev.statements
    assert out.narrative == "The old narrative."
    # spine taken from fresh (not prev)
    assert out.versions == fresh.versions
    assert out.committee_reports == fresh.committee_reports


def test_preserve_leg_history_reattaches_related_media() -> None:
    """should carry prev.related_media (Tier-2, expensive) onto the fresh spine"""
    media = RelatedMedia(
        title="Markup video", url="https://youtube.com/watch?v=abc", kind="video"
    )
    prev = LegHistory(related_media=[media], narrative="n")
    fresh = LegHistory()  # freshly re-derived spine has no related_media
    out = preserve_leg_history(prev, fresh)
    assert out.related_media == [media]


# --- apply_classifier_flip --------------------------------------------------


def test_apply_classifier_flip_in_scope_returns_bill_unchanged() -> None:
    """should be a no-op when classifier verdict is in_scope"""
    bill = _bill()
    out = apply_classifier_flip(bill, in_scope=True, rationale="ok", date=dt.date(2026, 6, 4))
    assert out is bill or out == bill
    assert out.tracking is True
    assert out.flipped_out is None


def test_apply_classifier_flip_out_of_scope_sets_tracking_false_and_audit() -> None:
    """should set tracking=False and populate flipped_out with date+reason"""
    bill = _bill()
    out = apply_classifier_flip(
        bill, in_scope=False, rationale="telehealth scope drift", date=dt.date(2026, 6, 4),
    )
    assert out.tracking is False
    expected_audit = FlipOutAudit(date=dt.date(2026, 6, 4), reason="telehealth scope drift")
    assert out.flipped_out == expected_audit


def test_apply_classifier_flip_raises_on_already_untracked() -> None:
    """should raise ValueError when the bill is already tracking=False"""
    bill = _bill(tracking=False)
    with pytest.raises(ValueError, match="already-untracked"):
        apply_classifier_flip(bill, in_scope=False, rationale="x", date=dt.date(2026, 6, 4))


# --- edge cases for defensive coverage ----------------------------------------


def test_detect_refreshable_returns_none_when_prev_untracked() -> None:
    """should return None even if fresh differs, when prev.tracking is False"""
    prev = _bill(tracking=False, update_date="2026-05-01T00:00:00Z")
    fresh = _bill(update_date="2026-05-03T00:00:00Z")
    assert detect_refreshable(prev, fresh) is None


def test_amendment_delta_returns_empty_when_fresh_empty() -> None:
    """should return empty tuple when fresh amendments list is empty"""
    from zwiadbrain.pipeline.refresh import _amendment_delta  # pyright: ignore[reportPrivateUsage]

    prev = [Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1))]
    assert _amendment_delta(prev, []) == ()


def test_amendment_delta_marks_all_as_new_when_prev_empty() -> None:
    """should return all fresh amendment numbers when prev is empty"""
    from zwiadbrain.pipeline.refresh import _amendment_delta  # pyright: ignore[reportPrivateUsage]

    fresh = [
        Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 5, 1)),
        Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 5, 2)),
    ]
    assert _amendment_delta([], fresh) == ("H.Amdt. 1", "H.Amdt. 2")


# --- clear_flip (F7 re-track) ----------------------------------------------


def test_clear_flip_retracks_a_flipped_out_bill() -> None:
    """should set tracking=True and clear flipped_out for an in-scope re-track"""
    from zwiadbrain.pipeline.refresh import clear_flip

    bill = _bill(
        tracking=False,
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="scope drift"),
    )
    out = clear_flip(bill)
    assert out.tracking is True
    assert out.flipped_out is None
    # topics / other fields untouched
    assert out.id == bill.id


def test_clear_flip_is_noop_on_already_tracking_bill() -> None:
    """should return an equivalent bill when it is already tracking with no flip audit"""
    from zwiadbrain.pipeline.refresh import clear_flip

    bill = _bill()  # tracking=True, flipped_out=None
    out = clear_flip(bill)
    assert out.tracking is True
    assert out.flipped_out is None


def test_amendment_delta_ignores_removed_amendment() -> None:
    """should NOT report an amendment that existed in prev but is gone from fresh"""
    from zwiadbrain.pipeline.refresh import _amendment_delta  # pyright: ignore[reportPrivateUsage]

    prev = [
        Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1)),
        Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 4, 2)),
    ]
    fresh = [Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1))]
    # H.Amdt. 2 was removed; the delta tracks only new/advanced amendments in fresh.
    assert _amendment_delta(prev, fresh) == ()


def test_amendment_delta_stable_under_reorder() -> None:
    """should report the same set regardless of fresh ordering, in fresh order"""
    from zwiadbrain.pipeline.refresh import _amendment_delta  # pyright: ignore[reportPrivateUsage]

    prev = [Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1))]
    fresh_a = [
        Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 5, 1)),  # new
        Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 5, 2)),  # advanced
    ]
    fresh_b = [
        Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 5, 2)),  # advanced
        Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 5, 1)),  # new
    ]
    # Same membership, each in its own fresh order.
    assert set(_amendment_delta(prev, fresh_a)) == {"H.Amdt. 1", "H.Amdt. 2"}
    assert _amendment_delta(prev, fresh_a) == ("H.Amdt. 2", "H.Amdt. 1")
    assert _amendment_delta(prev, fresh_b) == ("H.Amdt. 1", "H.Amdt. 2")


# --- detect_state_refreshable -----------------------------------------------

from zwiadbrain.pipeline.refresh import detect_state_refreshable  # noqa: E402


def _state_bill(**over: object) -> Bill:
    base: dict[str, object] = dict(
        id="ca-2023-sb-362", jurisdiction="US-CA", title="T", bill_number="SB 362",
        session="2023-2024 Regular Session", legiscan_bill_id=1789012,
        change_hash="hash-A", summary="alpha", tracking=True,
    )
    base.update(over)
    return Bill(**base)  # type: ignore[arg-type]


def test_detect_state_refreshable_none_when_hash_unchanged() -> None:
    """should return None when the change_hash matches (cheap gate)"""
    prev = _state_bill()
    fresh = _state_bill(summary="beta")  # other fields differ, but hash is the same
    assert detect_state_refreshable(prev, fresh) is None


def test_detect_state_refreshable_triggers_on_hash_change_and_summary() -> None:
    """should flag classifier+summarizer when the hash advanced and the summary_hash changed"""
    prev = _state_bill(change_hash="hash-A", summary_hash="sh-A")
    fresh = _state_bill(change_hash="hash-B", summary_hash="sh-B")
    result = detect_state_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is True
    assert result.needs_summarizer is True


def test_detect_state_refreshable_none_for_untracked_prev() -> None:
    """should never refresh a bill that is already untracked"""
    prev = _state_bill(tracking=False, change_hash="hash-A")
    fresh = _state_bill(change_hash="hash-B")
    assert detect_state_refreshable(prev, fresh) is None
