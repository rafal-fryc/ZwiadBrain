"""Tests for candidate discovery: the keyword recall filter and since-window helper."""

import datetime as dt

from zwiadbrain.models import Bill
from zwiadbrain.pipeline.discover import (
    discover_candidates,
    filter_unseen,
    keyword_filter,
    recall_filter,
)
from zwiadbrain.sources.base import Candidate


def _candidate(title: str) -> Candidate:
    return Candidate(source="fake", native_id=title, jurisdiction="US", title=title)


def _fed_candidate(native_id: str) -> Candidate:
    return Candidate(source="congress", native_id=native_id, jurisdiction="US", title=native_id)


class _FakeSource:
    name = "fake"

    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = candidates
        self.calls: list[tuple[dt.datetime | None, int]] = []

    def discover(
        self,
        *,
        congress: int | None = None,
        since: dt.datetime | None = None,
        limit: int = 20,
        max_pages: int = 1,
    ) -> list[Candidate]:
        self.calls.append((since, limit))
        return self._candidates[:limit]

    def fetch(self, native_id: str) -> Bill:
        raise NotImplementedError

    def fetch_policy_area(self, native_id: str) -> str | None:
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


class _PolicySource:
    """A source whose only meaningful capability is the policyArea probe."""

    name = "fake"

    def __init__(self, policy_by_id: dict[str, str | None]) -> None:
        self._policy = policy_by_id
        self.probed: list[str] = []

    def discover(
        self,
        *,
        congress: int | None = None,
        since: dt.datetime | None = None,
        limit: int = 20,
        max_pages: int = 1,
    ) -> list[Candidate]:
        return []

    def fetch(self, native_id: str) -> Bill:
        raise NotImplementedError

    def fetch_policy_area(self, native_id: str) -> str | None:
        self.probed.append(native_id)
        return self._policy.get(native_id)


def test_recall_filter_recovers_policy_area_misses() -> None:
    """should keep title matches and recover title-miss bills via an allowlisted policyArea"""
    cands = [
        _candidate("AI Accountability Act"),  # title seed -> Stage 1
        _candidate("Boring Banking Act"),  # title miss, Commerce -> Stage 2
        _candidate("Highway Funding Act"),  # title miss, Transportation -> dropped
    ]
    source = _PolicySource(
        {"Boring Banking Act": "Commerce", "Highway Funding Act": "Transportation"}
    )
    kept = recall_filter(
        cands, source, seeds=["ai"], policy_areas=["Commerce"], limit=10, max_probe=10
    )
    assert {c.native_id for c in kept} == {"AI Accountability Act", "Boring Banking Act"}
    # the Stage-1 title match is not re-probed; only the two title-misses are
    assert source.probed == ["Boring Banking Act", "Highway Funding Act"]


def test_recall_filter_respects_max_probe() -> None:
    """should probe at most max_probe of the title-miss candidates"""
    cands = [_candidate(f"Bill {i}") for i in range(5)]
    source = _PolicySource({c.native_id: "Commerce" for c in cands})
    kept = recall_filter(
        cands, source, seeds=["zzz"], policy_areas=["Commerce"], limit=10, max_probe=2
    )
    assert len(source.probed) == 2
    assert len(kept) == 2


def test_recall_filter_caps_to_limit_without_probing() -> None:
    """should cap to limit and skip the probe entirely once Stage 1 fills it"""
    cands = [_candidate("AI one"), _candidate("AI two"), _candidate("AI three")]
    source = _PolicySource({})
    kept = recall_filter(
        cands, source, seeds=["ai"], policy_areas=["Commerce"], limit=2, max_probe=10
    )
    assert len(kept) == 2
    assert source.probed == []


# --- filter_unseen: drop candidates already on the wiki (PHASE-22) ----------


def test_filter_unseen_drops_candidates_already_on_the_wiki() -> None:
    """should drop a candidate whose bill id is in known_ids, keep the rest"""
    cands = [_fed_candidate("118/hr/1"), _fed_candidate("118/hr/2")]
    kept = filter_unseen(cands, {"118-hr-1"})
    assert [c.native_id for c in kept] == ["118/hr/2"]


def test_filter_unseen_maps_native_id_slashes_to_bill_id_dashes() -> None:
    """should compare candidates by their bill-id form (slashes -> dashes)"""
    cands = [_fed_candidate("118/hr/2670")]
    assert filter_unseen(cands, {"118-hr-2670"}) == []


def test_filter_unseen_empty_known_keeps_everything() -> None:
    """should be a no-op when nothing is known yet"""
    cands = [_fed_candidate("118/hr/1"), _fed_candidate("118/s/2")]
    assert filter_unseen(cands, set()) == cands
