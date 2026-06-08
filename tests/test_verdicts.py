"""Tests for resumable verdict + summary application (backfill scaling gaps 1+2)."""

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.verdicts import Verdict, apply_summaries, split_by_verdict


def _bill(bill_id: str, *, summary: str | None = None) -> Bill:
    """A minimal state Bill (state jurisdiction avoids the federal id-shape validator)."""
    return Bill(
        id=bill_id, jurisdiction="US-CA", title=f"Bill {bill_id}",
        bill_number=bill_id.upper(), summary=summary,
    )


def test_split_by_verdict_applies_topics_to_in_scope() -> None:
    """should return in-scope candidates with the verdict's topics applied"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=["ai"])]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert [b.id for b in classified] == ["ca-2025-ab-1"]
    assert classified[0].topics == ["ai"]
    assert rejects == []
    assert pending == []


def test_split_by_verdict_routes_out_of_scope_to_rejects() -> None:
    """should route an out-of-scope verdict's candidate to rejects unchanged"""
    cands = [_bill("ca-2025-ab-2")]
    verdicts = [Verdict(id="ca-2025-ab-2", in_scope=False)]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert classified == []
    assert [b.id for b in rejects] == ["ca-2025-ab-2"]
    assert pending == []


def test_split_by_verdict_reports_unclassified_tail_as_pending() -> None:
    """should return a candidate with no verdict as pending (resumable tail), not emit it"""
    cands = [_bill("ca-2025-ab-1"), _bill("ca-2025-ab-2")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=["privacy"])]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert [b.id for b in classified] == ["ca-2025-ab-1"]
    assert rejects == []
    assert pending == ["ca-2025-ab-2"]


def test_split_by_verdict_unknown_verdict_id_raises() -> None:
    """should fail loud on a verdict id that matches no candidate (stale/typo guard)"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-99", in_scope=True, topics=["ai"])]
    with pytest.raises(ConfigError):
        split_by_verdict(cands, verdicts)


def test_split_by_verdict_in_scope_without_topics_raises() -> None:
    """should fail loud on an in-scope verdict that carries no topics"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=[])]
    with pytest.raises(ConfigError):
        split_by_verdict(cands, verdicts)


def test_apply_summaries_sets_summary_prose() -> None:
    """should replace each classified bill's summary from the {id: summary} map"""
    classified = [_bill("ca-2025-ab-1", summary="raw")]
    updated, pending = apply_summaries(classified, {"ca-2025-ab-1": "plain language"})
    assert updated[0].summary == "plain language"
    assert pending == []


def test_apply_summaries_reports_unsummarized_tail() -> None:
    """should return a classified bill with no summary entry as pending"""
    classified = [_bill("ca-2025-ab-1"), _bill("ca-2025-ab-2")]
    updated, pending = apply_summaries(classified, {"ca-2025-ab-1": "done"})
    assert updated[0].summary == "done"
    assert pending == ["ca-2025-ab-2"]


def test_apply_summaries_unknown_id_raises() -> None:
    """should fail loud on a summary id that matches no classified bill"""
    classified = [_bill("ca-2025-ab-1")]
    with pytest.raises(ConfigError):
        apply_summaries(classified, {"ca-2025-ab-99": "x"})


def test_apply_summaries_is_idempotent() -> None:
    """should be a stable no-op when re-applied with the same map (D20)"""
    classified = [_bill("ca-2025-ab-1")]
    once, _ = apply_summaries(classified, {"ca-2025-ab-1": "s"})
    twice, pending = apply_summaries(once, {"ca-2025-ab-1": "s"})
    assert twice[0].summary == "s"
    assert pending == []
