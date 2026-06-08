"""Resumable classification + summary application (backfill scaling gaps 1+2).

Classification verdicts (in/out + topics) and plain-language summaries are produced by
interactive-session subagents and persisted to JSON next to a run's candidates, so a plan
rate-limit or context cutoff only loses the unprocessed *tail*. ``split_by_verdict`` splits
candidates into in-scope (topics applied) + rejects from a verdict list; ``apply_summaries``
merges a ``{id: summary}`` map into the classified bills. The pure logic lives here; the CLI
wrappers (``apply-verdicts`` / ``apply-summaries``) live in ``cli.py`` — mirroring how
``rejects.py`` backs ``record-rejects``. See
docs/superpowers/specs/2026-06-08-backfill-scaling-gaps-design.md.
"""

from __future__ import annotations

from pydantic import BaseModel

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill


class Verdict(BaseModel):
    """One classifier verdict for a candidate bill (a transient staging artifact).

    ``reason`` keeps the classifier's rationale for the audit trail; it is not persisted
    to the wiki page (only ``topics`` and, later, the summary land on the ``Bill``).
    """

    id: str
    in_scope: bool
    topics: list[str] = []
    reason: str = ""


def split_by_verdict(
    candidates: list[Bill], verdicts: list[Verdict]
) -> tuple[list[Bill], list[Bill], list[str]]:
    """Split *candidates* into ``(classified, rejects, pending_ids)`` by their verdict.

    An in-scope verdict yields the candidate with ``topics`` applied; an out-of-scope verdict
    yields it unchanged into ``rejects``; a candidate with no verdict has its id returned in
    ``pending_ids`` (the unclassified tail — not emitted, not an error, so a rerun resumes).
    A verdict whose id matches no candidate, or an in-scope verdict with no topics, is a
    :class:`ConfigError` (a stale/typo verdict, or a classified-in bill missing its topic).
    Order is preserved.
    """
    by_id = {bill.id: bill for bill in candidates}
    verdict_by_id: dict[str, Verdict] = {}
    for verdict in verdicts:
        if verdict.id not in by_id:
            raise ConfigError(f"verdict id {verdict.id!r} matches no candidate")
        if verdict.in_scope and not verdict.topics:
            raise ConfigError(f"in-scope verdict {verdict.id!r} has no topics")
        verdict_by_id[verdict.id] = verdict
    classified: list[Bill] = []
    rejects: list[Bill] = []
    pending: list[str] = []
    for bill in candidates:
        verdict = verdict_by_id.get(bill.id)
        if verdict is None:
            pending.append(bill.id)
        elif verdict.in_scope:
            classified.append(bill.model_copy(update={"topics": verdict.topics}))
        else:
            rejects.append(bill)
    return classified, rejects, pending
