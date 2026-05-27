"""Tests for the enrichment seam: fetch via the source, stamp sync bookkeeping."""

import datetime as dt

from zwiadbrain.models import Bill
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.sources.base import Candidate


class _FakeSource:
    name = "fake"

    def __init__(self, bill: Bill) -> None:
        self._bill = bill
        self.fetched: list[str] = []

    def discover(self, *, since: dt.datetime | None = None, limit: int = 20) -> list[Candidate]:
        return []

    def fetch(self, native_id: str) -> Bill:
        self.fetched.append(native_id)
        return self._bill


def _candidate() -> Candidate:
    return Candidate(source="fake", native_id="118/hr/1", jurisdiction="US", title="t")


def test_enrich_fetches_by_native_id_and_stamps_last_synced() -> None:
    """should fetch the candidate and stamp a timezone-aware last_synced"""
    bill = Bill(id="118-hr-1", jurisdiction="US", title="A bill", bill_number="H.R. 1")
    source = _FakeSource(bill)
    out = enrich(source, _candidate())
    assert source.fetched == ["118/hr/1"]
    assert out.last_synced is not None
    assert out.last_synced.tzinfo is not None


def test_enrich_preserves_a_source_provided_last_synced() -> None:
    """should not overwrite last_synced if the source already set it"""
    stamped = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    bill = Bill(id="x", jurisdiction="US", title="t", bill_number="H.R. 1", last_synced=stamped)
    out = enrich(_FakeSource(bill), _candidate())
    assert out.last_synced == stamped
