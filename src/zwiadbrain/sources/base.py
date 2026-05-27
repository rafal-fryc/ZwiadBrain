"""The source abstraction shared by every data source.

A :class:`Source` does two things: ``discover`` surfaces lightweight
:class:`Candidate` records (enough to keyword-filter and classify), and ``fetch``
turns a single source-native id into a fully-mapped :class:`~zwiadbrain.models.Bill`.
Each source maps its own API onto the common model, so the pipeline never sees
source-specific JSON.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from zwiadbrain.models import Bill


class Candidate(BaseModel):
    """A discovered item, before enrichment — the unit ``discover`` yields."""

    source: str
    native_id: str
    jurisdiction: str
    title: str
    summary: str | None = None
    update_date: str | None = None  # the source's change cursor (e.g. Congress updateDate)
    raw: dict[str, object] = {}


@runtime_checkable
class Source(Protocol):
    """Structural contract every data source implements."""

    name: str

    def discover(self, *, since: dt.datetime | None = None, limit: int = 20) -> list[Candidate]:
        """Surface up to ``limit`` candidates changed since ``since`` (newest first)."""
        ...

    def fetch(self, native_id: str) -> Bill:
        """Fetch and map a single item to a fully-enriched :class:`Bill`."""
        ...
