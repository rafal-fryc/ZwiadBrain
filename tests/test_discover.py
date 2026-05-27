"""Tests for candidate discovery: the keyword recall filter and since-window helper."""

import datetime as dt

from zwiadbrain.models import Bill
from zwiadbrain.pipeline.discover import discover_candidates, keyword_filter
from zwiadbrain.sources.base import Candidate


def _candidate(title: str) -> Candidate:
    return Candidate(source="fake", native_id=title, jurisdiction="US", title=title)


class _FakeSource:
    name = "fake"

    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = candidates
        self.calls: list[tuple[dt.datetime | None, int]] = []

    def discover(self, *, since: dt.datetime | None = None, limit: int = 20) -> list[Candidate]:
        self.calls.append((since, limit))
        return self._candidates[:limit]

    def fetch(self, native_id: str) -> Bill:
        raise NotImplementedError


def test_keyword_filter_keeps_titles_matching_any_seed() -> None:
    """should keep candidates whose title contains any seed (case-insensitive)"""
    candidates = [
        _candidate("AI Accountability Act"),
        _candidate("Highway Funding Act"),
        _candidate("Data Broker Privacy Act"),
    ]
    seeds = ["artificial intelligence", "data broker", "ai "]
    kept = {c.title for c in keyword_filter(candidates, seeds)}
    assert kept == {"AI Accountability Act", "Data Broker Privacy Act"}


def test_keyword_filter_returns_all_when_no_seeds() -> None:
    """should treat absent seeds as 'no filter' and pass everything through"""
    candidates = [_candidate("one"), _candidate("two")]
    assert keyword_filter(candidates, None) == candidates
    assert keyword_filter(candidates, []) == candidates


def test_discover_candidates_filters_by_seed_and_caps_to_limit() -> None:
    """should oversample, keyword-filter, then return at most `limit` candidates"""
    source = _FakeSource(
        [
            _candidate("AI bill one"),
            _candidate("road bill"),
            _candidate("AI bill two"),
            _candidate("AI bill three"),
        ]
    )
    out = discover_candidates(source, seeds=["ai"], limit=2)
    assert len(out) == 2
    assert all("ai" in c.title.lower() for c in out)


def test_discover_candidates_forwards_since_to_source() -> None:
    """should pass the since-window through to the underlying source"""
    source = _FakeSource([])
    since = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    discover_candidates(source, since=since, limit=5)
    assert source.calls[0][0] == since
