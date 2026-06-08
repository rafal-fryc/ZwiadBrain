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
    """Keep candidates whose title OR summary contains any seed (case-insensitive).

    Absent or empty ``seeds`` means "no filter" — every candidate passes. The summary is
    consulted so state discovery (which carries the LegiScan ``description`` on
    ``Candidate.summary``) recalls on the bill text; federal candidates have no summary, so
    matching is title-only for them, unchanged.
    """
    if not seeds:
        return candidates
    lowered = [seed.lower() for seed in seeds]
    return [
        c
        for c in candidates
        if any(seed in f"{c.title} {c.summary or ''}".lower() for seed in lowered)
    ]


def filter_unseen(candidates: list[Candidate], known_ids: set[str]) -> list[Candidate]:
    """Drop candidates already on the wiki (PHASE-22).

    A candidate's ``native_id`` (``"congress/type/number"``) maps to a bill-id slug
    (``"congress-type-number"``) by swapping ``/`` for ``-``; a candidate whose slug is in
    *known_ids* (the existing wiki bill ids) is dropped so a re-run of a back-catalog sweep
    does not re-stage and re-classify bills that are already tracked. Order is preserved.
    Empty *known_ids* is a no-op (every candidate is unseen).
    """
    return [c for c in candidates if c.native_id.replace("/", "-") not in known_ids]


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


def recall_filter(
    candidates: list[Candidate],
    source: Source,
    *,
    seeds: list[str] | None,
    policy_areas: list[str],
    limit: int,
    max_probe: int,
) -> list[Candidate]:
    """Two-stage recall over an already-scanned candidate list (decision: PHASE-03.1).

    Stage 1 keeps candidates whose title matches a seed (free). Stage 2 probes up to
    ``max_probe`` of the *remaining* candidates' ``policyArea`` (one cheap request
    each via ``source.fetch_policy_area``) and keeps those in the ``policy_areas``
    allowlist — recovering topical bills whose title carries no seed. Returns at most
    ``limit`` candidates; probing stops early once ``limit`` is reached.
    """
    stage1 = keyword_filter(candidates, seeds)
    kept_ids = {c.native_id for c in stage1}
    result = list(stage1)
    allow = set(policy_areas)
    probed = 0
    for candidate in candidates:
        if len(result) >= limit:
            break
        if candidate.native_id in kept_ids or not allow or probed >= max_probe:
            continue
        probed += 1
        if source.fetch_policy_area(candidate.native_id) in allow:
            result.append(candidate)
    return result[:limit]
