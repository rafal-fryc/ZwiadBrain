"""Candidate discovery: the keyword recall filter and a since-window helper.

Discovery is the recall stage of the relevance pipeline (decision 17): a cheap
keyword pre-filter that narrows the candidate universe before the (later) Claude
precision classifier. ``keyword_filter`` is the shared primitive; the backfill
command and the eventual Pass-B scan both build on it.
"""

from __future__ import annotations

import datetime as dt

from zwiadbrain.sources.base import Candidate, Source

# Over-fetch factor so the keyword filter has room to discard before capping to limit.
_OVERSAMPLE = 5


def keyword_filter(candidates: list[Candidate], seeds: list[str] | None) -> list[Candidate]:
    """Keep candidates whose title contains any seed (case-insensitive).

    Absent or empty ``seeds`` means "no filter" — every candidate passes.
    """
    if not seeds:
        return candidates
    lowered = [seed.lower() for seed in seeds]
    return [c for c in candidates if any(seed in c.title.lower() for seed in lowered)]


def discover_candidates(
    source: Source,
    *,
    since: dt.datetime | None = None,
    seeds: list[str] | None = None,
    limit: int = 20,
) -> list[Candidate]:
    """Discover up to ``limit`` candidates from ``source``, keyword-filtered by ``seeds``."""
    fetch_limit = limit * _OVERSAMPLE if seeds else limit
    candidates = source.discover(since=since, limit=fetch_limit)
    return keyword_filter(candidates, seeds)[:limit]
