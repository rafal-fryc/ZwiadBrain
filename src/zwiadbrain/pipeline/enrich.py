"""Enrichment: turn a discovered candidate into a fully-populated ``Bill``.

The per-field mapping from a source's API onto :class:`~zwiadbrain.models.Bill`
lives in each source (so the pipeline stays source-agnostic). This module is the
source-agnostic seam that owns the cross-source post-processing — currently just
stamping ``last_synced``; the classification gate and change-hash policy attach
here in later phases.
"""

from __future__ import annotations

import datetime as dt

from zwiadbrain.models import Bill
from zwiadbrain.sources.base import Candidate, Source


def enrich(source: Source, candidate: Candidate) -> Bill:
    """Fetch the full bill for ``candidate`` from ``source`` and stamp sync time."""
    bill = source.fetch(candidate.native_id)
    if bill.last_synced is None:
        bill.last_synced = dt.datetime.now(dt.UTC)
    return bill
