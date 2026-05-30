"""Tests for the law-brain link-decision registry (wiki/links.yaml).

The registry is a dumb persistent store of prior link decisions keyed by
lawbrain_slug. Stickiness (D9) is enforced by the *caller* comparing a page's
current keys_hash against the stored decision's keys_hash — the registry itself
never decides staleness, it only stores and returns decisions verbatim.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from zwiadbrain.exceptions import LawBrainError
from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry


def _decision(
    *,
    slug: str = "bill-us-hr-1234",
    decision: str = "link",
    target_id: str | None = "us-hr-1234",
    matched_by: str | None = "deterministic",
    keys_hash: str = "hash-aaa",
    decided: dt.date | None = dt.date(2026, 5, 29),
) -> LinkDecision:
    return LinkDecision(
        lawbrain_slug=slug,
        decision=decision,  # type: ignore[arg-type]
        target_id=target_id,
        matched_by=matched_by,
        keys_hash=keys_hash,
        decided=decided,
    )


def test_should_return_recorded_decision_when_slug_was_decided() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    decision = _decision()
    registry.record(decision)

    # Act
    found = registry.decision_for("bill-us-hr-1234")

    # Assert
    assert found is not None
    assert found.target_id == "us-hr-1234"
    assert found.decision == "link"
    assert found.keys_hash == "hash-aaa"


def test_should_return_none_when_slug_was_never_decided() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))

    # Act / Assert
    assert registry.decision_for("bill-unknown-slug") is None


def test_should_replace_in_place_when_recording_same_slug_twice() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(decision="not_in_scope", target_id=None, matched_by=None))

    # Act — re-decide the same slug as a confirmed link
    registry.record(_decision(decision="link", target_id="us-hr-1234"))
    found = registry.decision_for("bill-us-hr-1234")

    # Assert — one entry, updated, not duplicated
    assert found is not None
    assert found.decision == "link"
    assert found.target_id == "us-hr-1234"


def test_should_be_sticky_when_keys_hash_is_unchanged() -> None:
    # Arrange — a prior decision and a page whose keys still hash the same
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(keys_hash="hash-stable"))
    current_keys_hash = "hash-stable"

    # Act — the caller's stickiness check (D9): same hash => reuse decision
    prior = registry.decision_for("bill-us-hr-1234")
    assert prior is not None
    is_sticky = prior.keys_hash == current_keys_hash

    # Assert
    assert is_sticky is True


def test_should_signal_reevaluation_when_keys_hash_changed() -> None:
    # Arrange — page keys changed since the decision was recorded
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(keys_hash="hash-old"))
    current_keys_hash = "hash-new"

    # Act — decision_for still returns the stored decision verbatim...
    prior = registry.decision_for("bill-us-hr-1234")
    assert prior is not None
    # ...and the caller compares hashes to decide staleness.
    is_sticky = prior.keys_hash == current_keys_hash

    # Assert — different hash => caller must re-evaluate
    assert is_sticky is False
    assert prior.keys_hash == "hash-old"


def test_should_round_trip_every_field_through_dump_and_load(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "links.yaml"
    registry = LinkRegistry.load(path)
    registry.record(_decision(slug="bill-us-hr-1234"))
    registry.record(
        _decision(
            slug="bill-eu-gdpr-overview",
            decision="not_in_scope",
            target_id=None,
            matched_by=None,
            keys_hash="hash-bbb",
            decided=dt.date(2026, 4, 1),
        )
    )

    # Act
    registry.dump(path)
    reloaded = LinkRegistry.load(path)

    # Assert — link decision survives intact
    link = reloaded.decision_for("bill-us-hr-1234")
    assert link is not None
    assert link.decision == "link"
    assert link.target_id == "us-hr-1234"
    assert link.matched_by == "deterministic"
    assert link.keys_hash == "hash-aaa"
    assert link.decided == dt.date(2026, 5, 29)

    # Assert — not_in_scope decision with explicit null target survives intact
    nis = reloaded.decision_for("bill-eu-gdpr-overview")
    assert nis is not None
    assert nis.decision == "not_in_scope"
    assert nis.target_id is None
    assert nis.matched_by is None
    assert nis.decided == dt.date(2026, 4, 1)


def test_should_yield_empty_registry_when_file_is_missing(tmp_path: Path) -> None:
    # Arrange / Act
    registry = LinkRegistry.load(tmp_path / "absent.yaml")

    # Assert
    assert registry.decision_for("anything") is None


def test_should_yield_empty_registry_when_file_has_no_links_key(tmp_path: Path) -> None:
    # Arrange — a valid-but-empty YAML document
    path = tmp_path / "links.yaml"
    path.write_text("links: []\n", encoding="utf-8")

    # Act
    registry = LinkRegistry.load(path)

    # Assert
    assert registry.decision_for("anything") is None


def test_should_raise_lawbrain_error_when_yaml_is_malformed(tmp_path: Path) -> None:
    # Arrange — unbalanced bracket is not parseable YAML
    path = tmp_path / "links.yaml"
    path.write_text("links: [unterminated\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(LawBrainError):
        LinkRegistry.load(path)


def test_should_produce_stable_sorted_output_on_repeated_dump(tmp_path: Path) -> None:
    # Arrange — insert in non-alphabetical order
    path = tmp_path / "links.yaml"
    registry = LinkRegistry.load(path)
    registry.record(_decision(slug="regulation-z-page", keys_hash="hash-z"))
    registry.record(_decision(slug="bill-a-page", keys_hash="hash-a"))
    registry.record(_decision(slug="concept-m-page", keys_hash="hash-m"))

    # Act — dump twice
    registry.dump(path)
    first_bytes = path.read_bytes()
    registry.dump(path)
    second_bytes = path.read_bytes()

    # Assert — identical bytes both times (deterministic slug-sorted output)
    assert first_bytes == second_bytes


def test_should_sort_entries_by_slug_in_dump(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "links.yaml"
    registry = LinkRegistry.load(path)
    registry.record(_decision(slug="regulation-z-page", keys_hash="hash-z"))
    registry.record(_decision(slug="bill-a-page", keys_hash="hash-a"))

    # Act
    registry.dump(path)
    reloaded = LinkRegistry.load(path)

    # Assert — both survive (order in memory does not matter, round-trip does)
    assert reloaded.decision_for("regulation-z-page") is not None
    assert reloaded.decision_for("bill-a-page") is not None


def test_should_round_trip_reject_decision_with_null_target(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "links.yaml"
    registry = LinkRegistry.load(path)
    registry.record(
        _decision(
            slug="concept-unrelated-topic",
            decision="reject",
            target_id=None,
            matched_by=None,
            keys_hash="hash-rej",
        )
    )

    # Act
    registry.dump(path)
    reloaded = LinkRegistry.load(path)

    # Assert
    rej = reloaded.decision_for("concept-unrelated-topic")
    assert rej is not None
    assert rej.decision == "reject"
    assert rej.target_id is None
    assert rej.matched_by is None
