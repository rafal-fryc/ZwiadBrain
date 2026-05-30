"""Durable registry of law-brain link decisions (``wiki/links.yaml``).

A :class:`LinkDecision` is the persistent record of "we already decided about
this law-brain page": link it to a tracked target, mark it out of scope, or
reject it. Each decision snapshots the page's ``keys_hash`` at decision time.

Stickiness (D9) is enforced by the *caller*, not here: ``decision_for`` returns
the stored decision verbatim, and the caller compares the page's current
``keys_hash`` against ``decision.keys_hash`` — equal means reuse the decision,
different means the underlying keys moved and the page must be re-evaluated.
Keeping that comparison in the caller leaves this module a dumb store and the
staleness rule expressed in exactly one place (the ``fetch-lawbrain-candidates``
half).

The on-disk shape is a single ``links:`` list under the YAML root, mirroring the
``topics.yaml`` loader idiom (``yaml.safe_load`` + a pydantic model, with
``yaml.YAMLError`` mapped to a project exception).

YAML shape example (``wiki/links.yaml``)::

    links:
      - lawbrain_slug: regulation-california-sb53-tfaia
        decision: link
        target_id: ca-2025-sb-53
        matched_by: deterministic
        keys_hash: 3f1a9c...
        decided: 2026-05-29
      - lawbrain_slug: regulation-gdpr
        decision: not_in_scope
        target_id: null
        matched_by: null
        keys_hash: 9c0b2d...
        decided: 2026-05-29
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError

from zwiadbrain.exceptions import LawBrainError


class LinkDecision(BaseModel):
    """One recorded decision about a single law-brain page.

    ``keys_hash`` is the hash of the page's extracted keys at decision time; the
    caller compares it against the page's current keys_hash to honor D9.
    ``target_id`` and ``matched_by`` are ``None`` for ``not_in_scope`` and
    ``reject`` decisions and serialize explicitly as ``null`` in YAML so the
    round-trip is lossless.
    """

    lawbrain_slug: str
    decision: Literal["link", "not_in_scope", "reject"]
    target_id: str | None = None
    matched_by: str | None = None
    keys_hash: str
    decided: dt.date | None = None


class _LinksFile(BaseModel):
    """Typed wrapper for the top-level ``links.yaml`` document.

    Using a pydantic wrapper (not manual dict access) keeps pyright --strict
    happy: ``model_validate`` accepts ``Any`` and returns a fully typed model.
    An absent or empty ``links`` key is valid and yields an empty list.
    """

    links: list[LinkDecision] = []


class LinkRegistry:
    """In-memory view of ``wiki/links.yaml`` keyed by ``lawbrain_slug``.

    The registry is a dumb persistent store.  Callers decide whether a stored
    decision is still valid by comparing ``keys_hash`` values — this class never
    makes that judgment (D9).
    """

    def __init__(self, decisions: list[LinkDecision] | None = None) -> None:
        # Dict keyed by slug so record() is last-write-wins and never duplicates.
        self._by_slug: dict[str, LinkDecision] = {
            d.lawbrain_slug: d for d in (decisions or [])
        }

    @classmethod
    def load(cls, path: Path) -> LinkRegistry:
        """Load decisions from *path*.

        A missing file yields an empty registry (first run).  Unparseable YAML or
        a malformed ``links`` entry raises :class:`~zwiadbrain.exceptions.LawBrainError`.
        """
        if not path.exists():
            return cls([])
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise LawBrainError(f"link registry is not valid YAML: {path}") from exc
        if raw is None:
            return cls([])
        try:
            parsed = _LinksFile.model_validate(raw)
        except ValidationError as exc:
            raise LawBrainError(
                f"link registry is malformed: {path}\n{exc}"
            ) from exc
        return cls(parsed.links)

    def decision_for(self, slug: str) -> LinkDecision | None:
        """Return the stored decision for *slug*, or ``None`` if never decided.

        Returns the decision verbatim — staleness (the keys_hash comparison) is
        the caller's responsibility, not this method's.
        """
        return self._by_slug.get(slug)

    def record(self, decision: LinkDecision) -> None:
        """Insert or replace the decision for ``decision.lawbrain_slug`` in place."""
        self._by_slug[decision.lawbrain_slug] = decision

    def dump(self, path: Path) -> None:
        """Write all decisions to *path* as a slug-sorted ``links:`` YAML list.

        ``exclude_none=False`` keeps ``target_id: null`` / ``matched_by: null``
        explicit so out-of-scope and reject decisions round-trip through ``load``
        without information loss.  Entries are sorted by ``lawbrain_slug`` for
        deterministic, diff-friendly output (D20-friendly).
        """
        ordered = sorted(self._by_slug.values(), key=lambda d: d.lawbrain_slug)
        payload: dict[str, Any] = {
            "links": [d.model_dump(mode="json", exclude_none=False) for d in ordered]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
