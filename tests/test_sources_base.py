"""Tests for the source abstraction: the Candidate model and Source protocol."""

import datetime as dt

from zwiadbrain.models import Bill
from zwiadbrain.sources.base import Candidate, Source


def test_candidate_defaults_optional_fields() -> None:
    """should default summary/update_date to None and raw to an empty dict"""
    candidate = Candidate(
        source="congress", native_id="118/hr/1", jurisdiction="US", title="A bill"
    )
    assert candidate.summary is None
    assert candidate.update_date is None
    assert candidate.raw == {}


def test_source_protocol_is_satisfied_structurally() -> None:
    """should recognize a class with name/discover/fetch/fetch_policy_area as a Source"""

    class _FakeSource:
        name = "fake"

        def discover(self, *, since: dt.datetime | None = None, limit: int = 20) -> list[Candidate]:
            return []

        def fetch(self, native_id: str) -> Bill:
            return Bill(id=native_id, jurisdiction="US", title="t", bill_number="HR 1")

        def fetch_policy_area(self, native_id: str) -> str | None:
            return None

    assert isinstance(_FakeSource(), Source)
