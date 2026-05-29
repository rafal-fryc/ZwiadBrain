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

from zwiadbrain.models import Bill
from zwiadbrain.pipeline.refresh import summary_hash
from zwiadbrain.sources.base import Candidate, Source


def enrich(source: Source, candidate: Candidate) -> Bill:
    """Fetch the full bill for ``candidate`` and stamp the cross-source cursors."""
    bill = source.fetch(candidate.native_id)
    if bill.last_synced is None:
        bill.last_synced = dt.datetime.now(dt.UTC)
    bill.summary_hash = summary_hash(bill.summary)
    bill.amendments_count = len(bill.amendments)
    return bill
