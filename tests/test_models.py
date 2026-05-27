"""Tests for ZwiadBrain pydantic data models.

These pin the behavioural contract that matters downstream: the discriminated
union routes by `type`, required identifiers are enforced, list fields default
empty, and a parsed item round-trips through `model_dump`.
"""

import pytest
from pydantic import ValidationError

from zwiadbrain.models import (
    Bill,
    CommentarySource,
    EnforcementAction,
    parse_wiki_item,
)


def test_parse_wiki_item_routes_bill_by_type_discriminator() -> None:
    """should return a Bill when type == 'bill'"""
    item = parse_wiki_item(
        {
            "id": "us-ca-sb-362",
            "type": "bill",
            "jurisdiction": "US-CA",
            "title": "California Delete Act",
            "bill_number": "SB 362",
        }
    )
    assert isinstance(item, Bill)
    assert item.bill_number == "SB 362"


def test_parse_wiki_item_routes_enforcement_by_type_discriminator() -> None:
    """should return an EnforcementAction when type == 'enforcement'"""
    item = parse_wiki_item(
        {
            "id": "ftc-betterhelp",
            "type": "enforcement",
            "jurisdiction": "US",
            "title": "FTC v. BetterHelp",
            "agency": "FTC",
        }
    )
    assert isinstance(item, EnforcementAction)
    assert item.agency == "FTC"


def test_bill_requires_bill_number() -> None:
    """should reject a bill with no bill_number"""
    with pytest.raises(ValidationError):
        Bill.model_validate({"id": "x", "jurisdiction": "US-CA", "title": "t"})


def test_enforcement_requires_agency() -> None:
    """should reject an enforcement action with no agency"""
    with pytest.raises(ValidationError):
        EnforcementAction.model_validate({"id": "x", "jurisdiction": "US", "title": "t"})


def test_commentary_sources_default_to_empty_list() -> None:
    """should default commentary_sources to an empty list"""
    bill = Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1")
    assert bill.commentary_sources == []


def test_commentary_source_rejects_unknown_matched_by() -> None:
    """should constrain matched_by to the known matching strategies"""
    with pytest.raises(ValidationError):
        CommentarySource.model_validate(
            {
                "path": "wiki/regulation-x.md",
                "slug": "regulation-x",
                "content_hash": "deadbeef",
                "matched_by": "telepathy",
                "confidence": 1.0,
            }
        )


def test_list_defaults_are_not_shared_between_instances() -> None:
    """should give each instance its own list, not a shared mutable default"""
    a = Bill(id="a", jurisdiction="US", title="t", bill_number="SB 1")
    b = Bill(id="b", jurisdiction="US", title="t", bill_number="SB 2")
    a.topics.append("ai")
    assert b.topics == []


def test_wiki_item_round_trips_through_dump_and_parse() -> None:
    """should survive model_dump -> parse_wiki_item preserving its concrete type"""
    bill = Bill(id="x", jurisdiction="US-CA", title="t", bill_number="SB 1")
    again = parse_wiki_item(bill.model_dump())
    assert isinstance(again, Bill)
    assert again == bill
