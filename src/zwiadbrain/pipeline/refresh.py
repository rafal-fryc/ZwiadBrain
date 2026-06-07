"""Pure functions and the dataclass that drive the PHASE-06 watchlist refresh.

Nothing here does I/O.  The CLI commands (``fetch-refreshable``,
``render-refreshed``) compose these helpers with the source clients and the
renderer.

The trust boundary this module enforces:

* :func:`detect_refreshable` decides whether a bill is refreshable at all and,
  if so, which subagents the slash command needs to dispatch.  A bill whose
  Congress.gov ``updateDate`` is unchanged is NEVER refreshable, even if the
  other cursors look different (this is the cheap "any change" gate).

* :func:`preserve_leg_history` carries PHASE-05's expensive cross-modal-verified
  hearings + statements + narrative across a spine re-derive, per D38 + D40.

* :func:`apply_classifier_flip` is the only place that flips
  ``Bill.tracking`` to ``False`` and records the audit.  It refuses to operate
  on an already-untracked bill so the slash command can't double-flip.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field

from zwiadbrain.models import Amendment, Bill, FlipOutAudit, LegHistory


def summary_hash(summary: str | None) -> str | None:
    """sha256 hex of whitespace-collapsed *summary*, or ``None`` when no summary.

    Whitespace normalization matches :mod:`zwiadbrain.pipeline.enrich` so the
    two places that compute the cursor agree byte-for-byte on input.
    """
    if not summary or not summary.strip():
        return None
    normalized = " ".join(summary.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RefreshableBill:
    """A bill detected as refreshable, with the slash-command triggers computed.

    *changed_amendment_numbers* lists amendments whose ``number`` is new in
    *fresh* OR whose ``latest_action_date`` advanced since *prev*.  An unchanged
    amendment (same number + same date) is NOT included — the explainer is
    dispatched only on real change, not on every amendment for the whole bill.
    """

    prev: Bill
    fresh: Bill
    needs_classifier: bool
    needs_summarizer: bool
    changed_amendment_numbers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_explainer(self) -> bool:
        """True when there is at least one new or date-advanced amendment."""
        return bool(self.changed_amendment_numbers)


def _amendment_delta(prev: list[Amendment], fresh: list[Amendment]) -> tuple[str, ...]:
    """Return the amendment numbers that need re-explaining.

    An amendment is in the delta when its number is not in *prev*, OR when its
    ``latest_action_date`` differs from the prev entry's date (including a None
    → date transition).  Order matches *fresh*'s order, deduped.

    Removals are intentionally NOT reported: an amendment present in *prev* but
    absent from *fresh* produces no delta entry, because the explainer is
    dispatched only to (re-)describe amendments that still exist.  Membership of
    the result is therefore independent of *fresh*'s ordering; only the order of
    the returned tuple follows *fresh*.
    """
    prev_by_number: dict[str, Amendment] = {a.number: a for a in prev}
    out: list[str] = []
    seen: set[str] = set()
    for a in fresh:
        if a.number in seen:
            continue
        old = prev_by_number.get(a.number)
        if old is None or old.latest_action_date != a.latest_action_date:
            out.append(a.number)
            seen.add(a.number)
    return tuple(out)


def detect_refreshable(prev: Bill, fresh: Bill) -> RefreshableBill | None:
    """Return a :class:`RefreshableBill` when *fresh* differs from *prev*, else ``None``.

    Trigger logic (matches the PHASE-06 spec §3 matrix):

    * If ``prev.update_date == fresh.update_date`` → ``None`` (any-change gate
      failed; the cheap path).
    * Otherwise the bill is refreshable.  ``needs_classifier`` and
      ``needs_summarizer`` are True when EITHER ``update_date_text`` advanced
      OR ``summary_hash`` differs.  ``changed_amendment_numbers`` is the result
      of :func:`_amendment_delta`.

    A previously-untracked bill (``prev.tracking is False``) is treated as not
    refreshable — the caller must not have included it in
    ``refreshable.json``.  Defensive: we return ``None`` rather than raise so a
    rogue input cannot abort a bulk refresh.
    """
    if not prev.tracking:
        return None
    if prev.update_date == fresh.update_date:
        return None
    text_changed = (
        prev.update_date_text != fresh.update_date_text
        or prev.summary_hash != fresh.summary_hash
    )
    changed = _amendment_delta(prev.amendments, fresh.amendments)
    return RefreshableBill(
        prev=prev,
        fresh=fresh,
        needs_classifier=text_changed,
        needs_summarizer=text_changed,
        changed_amendment_numbers=changed,
    )


def detect_state_refreshable(prev: Bill, fresh: Bill) -> RefreshableBill | None:
    """State analog of :func:`detect_refreshable`, gated on LegiScan ``change_hash``.

    The cheap gate is the ``change_hash`` (the authoritative LegiScan cursor), not
    ``update_date``. When the hash advanced, ``needs_classifier``/``needs_summarizer``
    are True if the summary changed, and ``changed_amendment_numbers`` is the amendment
    delta — reusing the federal trigger logic. An already-untracked ``prev`` is never
    refreshable.
    """
    if not prev.tracking:
        return None
    if prev.change_hash == fresh.change_hash:
        return None
    text_changed = prev.summary_hash != fresh.summary_hash
    changed = _amendment_delta(prev.amendments, fresh.amendments)
    return RefreshableBill(
        prev=prev,
        fresh=fresh,
        needs_classifier=text_changed,
        needs_summarizer=text_changed,
        changed_amendment_numbers=changed,
    )


def preserve_leg_history(prev: LegHistory | None, fresh_spine: LegHistory) -> LegHistory:
    """Re-attach *prev*'s hearings/statements/narrative onto a freshly assembled spine.

    Implements the D38 + D40 preservation rule: the spine fields (``versions``,
    ``committee_reports``, ``votes``, ``floor_consideration``, ``conference``,
    ``enactment``) come from *fresh_spine* (re-derived from the API); the
    expensive cross-modal-verified research (``hearings``, ``statements``,
    ``related_media``) and the narrative come from *prev*.  Returns *fresh_spine*
    unchanged when *prev* is ``None`` (e.g. a non-enacted bill or a bill that never
    had leg-history assembled).
    """
    if prev is None:
        return fresh_spine
    return fresh_spine.model_copy(
        update={
            "hearings": prev.hearings,
            "statements": prev.statements,
            "related_media": prev.related_media,
            "narrative": prev.narrative,
        }
    )


def apply_classifier_flip(
    bill: Bill,
    *,
    in_scope: bool,
    rationale: str,
    date: dt.date,
) -> Bill:
    """Return a copy of *bill* reflecting the classifier's verdict.

    * ``in_scope=True`` → returns *bill* unchanged.
    * ``in_scope=False`` → returns a copy with ``tracking=False`` and
      ``flipped_out`` populated.  The existing ``topics`` are NOT cleared (the
      record of the prior classification stands).

    Raises :class:`ValueError` when called on an already-``tracking=False`` bill
    — that case never reaches the refresh pipeline because untracked bills are
    excluded from ``refreshable.json`` by ``fetch-refreshable``.
    """
    if not bill.tracking:
        raise ValueError(f"apply_classifier_flip on already-untracked bill: {bill.id}")
    if in_scope:
        return bill
    return bill.model_copy(
        update={
            "tracking": False,
            "flipped_out": FlipOutAudit(date=date, reason=rationale),
        }
    )


def clear_flip(bill: Bill) -> Bill:
    """Return a copy of *bill* re-tracked: ``tracking=True`` and ``flipped_out`` cleared.

    The inverse of :func:`apply_classifier_flip`'s OUT path, used by the
    ``--force`` re-track (F7) once the interactive classifier has judged a
    previously flipped-out bill in-scope again.  Idempotent on an
    already-tracking bill (returns an equivalent copy).  The existing ``topics``
    and all other fields are untouched.
    """
    return bill.model_copy(update={"tracking": True, "flipped_out": None})
