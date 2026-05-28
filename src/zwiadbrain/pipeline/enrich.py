"""Enrichment: turn a discovered candidate into a fully-populated ``Bill``.

The per-field mapping from a source's API onto :class:`~zwiadbrain.models.Bill`
lives in each source (so the pipeline stays source-agnostic). This module is the
source-agnostic seam that owns the cross-source post-processing: stamping
``last_synced``, deriving ``summary_hash`` from the CRS summary text, and
caching the amendments count so PHASE-06's refresh can detect amendment growth
without re-comparing the full list.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from zwiadbrain.models import Bill
from zwiadbrain.sources.base import Candidate, Source


def _summary_hash(summary: str | None) -> str | None:
    """sha256 hex of whitespace-collapsed summary, or ``None`` when no summary.

    Whitespace normalization mirrors the deterministic-render contract used
    elsewhere in the codebase so a Congress-side reformatting that only changes
    whitespace does not spuriously dirty the cursor.
    """
    if not summary:
        return None
    normalized = " ".join(summary.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def enrich(source: Source, candidate: Candidate) -> Bill:
    """Fetch the full bill for ``candidate`` and stamp the cross-source cursors."""
    bill = source.fetch(candidate.native_id)
    if bill.last_synced is None:
        bill.last_synced = dt.datetime.now(dt.UTC)
    bill.summary_hash = _summary_hash(bill.summary)
    bill.amendments_count = len(bill.amendments)
    return bill
