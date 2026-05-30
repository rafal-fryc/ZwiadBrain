from zwiadbrain.pipeline.lawbrain_review import (
    ReviewEntry,
    parse_review_queue,
    render_review_queue,
)


def test_review_entry_defaults_to_pending_status() -> None:
    # Arrange / Act
    entry = ReviewEntry(
        slug="regulation-take-it-down-act",
        target_id="ftc-2026-nudify-tool-operators",
        reason="weak-grounding",
    )
    # Assert
    assert entry.status == "pending"


def test_render_review_queue_emits_one_checklist_line_per_entry() -> None:
    # Arrange
    entries = [
        ReviewEntry(
            slug="regulation-take-it-down-act",
            target_id="ftc-2026-nudify-tool-operators",
            reason="weak-grounding",
        ),
        ReviewEntry(
            slug="concept-state-ai-chatbot-tracker",
            target_id=None,
            reason="low-confidence",
        ),
    ]
    # Act
    text = render_review_queue(entries)
    # Assert
    assert text.splitlines() == [
        "- [pending] regulation-take-it-down-act"
        " -> ftc-2026-nudify-tool-operators (weak-grounding)",
        "- [pending] concept-state-ai-chatbot-tracker -> None (low-confidence)",
    ]


def test_render_then_parse_round_trips() -> None:
    # Arrange
    entries = [
        ReviewEntry(
            slug="regulation-take-it-down-act",
            target_id="ftc-2026-nudify-tool-operators",
            reason="weak-grounding",
            status="pending",
        ),
        ReviewEntry(
            slug="regulation-collision-foo",
            target_id="ftc-2026-bar",
            reason="collision",
            status="pending",
        ),
        ReviewEntry(
            slug="concept-state-ai-chatbot-tracker",
            target_id=None,
            reason="stale",
            status="pending",
        ),
    ]
    # Act
    parsed = parse_review_queue(render_review_queue(entries))
    # Assert
    assert parsed == entries


def test_parse_review_queue_reads_accept_and_reject_tokens() -> None:
    # Arrange
    text = "\n".join(
        [
            "- [accept] regulation-california-sb53-tfaia -> ca-2025-sb-53 (collision)",
            "- [reject] concept-state-ai-chatbot-tracker -> None (low-confidence)",
        ]
    )
    # Act
    parsed = parse_review_queue(text)
    # Assert
    assert parsed[0].status == "accept"
    assert parsed[0].slug == "regulation-california-sb53-tfaia"
    assert parsed[0].target_id == "ca-2025-sb-53"
    assert parsed[0].reason == "collision"
    assert parsed[1].status == "reject"
    assert parsed[1].target_id is None
    assert parsed[1].reason == "low-confidence"


def test_parse_review_queue_ignores_blank_and_non_entry_lines() -> None:
    # Arrange — a header and a blank line surround a single real entry
    text = "\n".join(
        [
            "# Review queue",
            "",
            "- [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (stale)",
            "",
        ]
    )
    # Act
    parsed = parse_review_queue(text)
    # Assert
    assert len(parsed) == 1
    assert parsed[0].slug == "regulation-take-it-down-act"
    assert parsed[0].status == "pending"


def test_render_review_queue_empty_returns_empty_string() -> None:
    # Arrange / Act / Assert
    assert render_review_queue([]) == ""
