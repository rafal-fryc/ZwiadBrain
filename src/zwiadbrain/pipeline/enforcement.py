"""Pure matching/confirm/merge helpers for enforcement-matter consolidation.

Nothing here does I/O. The CLI render half composes these with the renderer to decide
new-vs-consolidate and to fold a new feed item into an existing matter idempotently.
The deterministic confirm here is the trust boundary that grounds the LLM matcher's
proposal (D53), mirroring how render-leg-history re-checks the verifier in Python.

When a match date is absent on either side there is no date proximity to lean on, so
:func:`confirm_match` demands a stronger respondent overlap (``missing_date_overlap_floor``)
before it will confirm — date proximity and respondent overlap are the two independent
signals, and dropping one tightens the other.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment

# Tokens dropped from a respondent name before overlap scoring (corporate suffixes /
# noise), so "Acme, Inc." and "Acme Corporation" compare as the same entity.
_STOPWORDS: frozenset[str] = frozenset(
    {"inc", "incorporated", "llc", "llp", "lp", "co", "corp", "corporation",
     "company", "ltd", "limited", "the", "and", "of"}
)


class MatterRef(BaseModel):
    """A lightweight reference to an existing tracked matter (matters.json entry)."""

    id: str
    agency_slug: str
    jurisdiction: str
    respondent: str | None = None
    date_filed: dt.date | None = None
    strong_key: str | None = None


def _tokens(name: str | None) -> frozenset[str]:
    raw = (name or "").lower().replace(",", " ").replace(".", " ")
    return frozenset(t for t in raw.split() if t and t not in _STOPWORDS)


def respondent_overlap(a: str | None, b: str | None) -> float:
    """Jaccard overlap of significant tokens in two respondent names (0.0-1.0)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _within(d1: dt.date | None, d2: dt.date | None, window_days: int) -> bool:
    if d1 is None or d2 is None:
        return True  # unknown date never *blocks* a match; respondent + key carry it
    return abs((d1 - d2).days) <= window_days


def build_shortlist(
    *,
    agency_slug: str,
    respondent: str | None,
    date: dt.date | None,
    matters: list[MatterRef],
    window_days: int,
    overlap_floor: float = 0.34,
) -> list[MatterRef]:
    """Candidate existing matters for the LLM matcher: same agency, overlapping
    respondent, date within the window. Sorted by descending respondent overlap."""
    scored = [
        (respondent_overlap(respondent, m.respondent), m)
        for m in matters
        if m.agency_slug == agency_slug and _within(date, m.date_filed, window_days)
    ]
    return [m for score, m in sorted(scored, key=lambda s: -s[0]) if score >= overlap_floor]


def confirm_match(
    *,
    item_respondent: str | None,
    item_date: dt.date | None,
    candidate_respondent: str | None,
    candidate_date: dt.date | None,
    confidence: float,
    min_confidence: float,
    window_days: int,
    overlap_floor: float = 0.34,
    missing_date_overlap_floor: float = 0.6,
) -> bool:
    """Deterministic grounding of an LLM-proposed match (D53). Confidence must clear
    the floor; then EITHER both dates are known (overlap >= overlap_floor AND within the
    window) OR a date is missing (no proximity to lean on, so require the stronger
    missing_date_overlap_floor on respondent overlap)."""
    if confidence < min_confidence:
        return False
    overlap = respondent_overlap(item_respondent, candidate_respondent)
    if item_date is not None and candidate_date is not None:
        return overlap >= overlap_floor and _within(item_date, candidate_date, window_days)
    return overlap >= missing_date_overlap_floor


def merge_developments(
    existing: list[EnforcementDevelopment], new: EnforcementDevelopment
) -> list[EnforcementDevelopment]:
    """Append *new* to *existing*, deduped by source_url, sorted by (date, source_url).

    Re-seeing the same source_url is a no-op (returns the existing list unchanged), so a
    repeated scan is idempotent.
    """
    if any(str(d.source_url) == str(new.source_url) for d in existing):
        return existing
    combined = [*existing, new]
    return sorted(combined, key=lambda d: (d.date or dt.date.min, str(d.source_url)))


def merge_current_state(
    existing: EnforcementAction,
    *,
    status: str | None,
    date_resolved: dt.date | None,
    penalties: str | None,
    outcome: str | None,
    significance: str | None,
) -> EnforcementAction:
    """Return a copy of *existing* with non-null new values applied (monotonic): a null
    new field never blanks an existing value."""
    updates: dict[str, object] = {}
    for field, value in (
        ("status", status), ("date_resolved", date_resolved),
        ("penalties", penalties), ("outcome", outcome), ("significance", significance),
    ):
        if value is not None:
            updates[field] = value
    return existing.model_copy(update=updates)
