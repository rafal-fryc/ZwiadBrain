"""Review queue for uncertain law-brain commentary proposals (PHASE-09, D61).

A pure render/parse pair over the committed-but-transient ``wiki/review-queue.md``
checklist. Uncertain proposals (low-confidence, key collision, LLM weak-grounding,
or a stale source page) are emitted as ``[pending]`` lines; the operator flips a
line to ``[accept]`` or ``[reject]`` and the render half (``render-lawbrain-commentary``)
reads the resolved tokens back, applies them, and prunes the queue in one pass.

This module does no I/O: it converts between a list of :class:`ReviewEntry` and the
markdown text. The render half owns reading/writing the file.

Line format (one checklist item per entry)::

    - [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (weak-grounding)

``target_id`` renders as the literal ``None`` when an entry has no target (e.g. a
``stale`` block whose source page vanished). Lines that do not match the format
(headers, blanks, prose) are ignored on parse, so the operator can annotate freely.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

ReviewReason = Literal["low-confidence", "collision", "weak-grounding", "stale"]
ReviewStatus = Literal["pending", "accept", "reject"]


class ReviewEntry(BaseModel):
    slug: str
    target_id: str | None
    reason: ReviewReason
    status: ReviewStatus = "pending"


# - [<status>] <slug> -> <target_id> (<reason>)
# target_id is a token run (no spaces) or the literal "None"; reason is one of the
# fixed set. The capture groups partition a well-formed line losslessly.
_ENTRY_RE = re.compile(
    r"^- \[(pending|accept|reject)\] (\S+) -> (\S+) "
    r"\((low-confidence|collision|weak-grounding|stale)\)$"
)


def render_review_queue(entries: list[ReviewEntry]) -> str:
    """Render *entries* as a markdown checklist, one ``- [status] ...`` line each.

    Entries are rendered in the order given (the render half decides ordering).
    A ``None`` *target_id* renders as the literal ``None``. Returns the empty
    string for an empty list (no trailing newline to add).
    """
    return "\n".join(
        f"- [{e.status}] {e.slug} -> {e.target_id if e.target_id is not None else 'None'} "
        f"({e.reason})"
        for e in entries
    )


def parse_review_queue(text: str) -> list[ReviewEntry]:
    """Parse review-queue markdown back into :class:`ReviewEntry` objects.

    The inverse of :func:`render_review_queue` for well-formed lines. Lines that do
    not match the checklist format (headers, blank lines, free-form notes) are
    skipped, so the file may carry an operator-authored header without breaking the
    round-trip. The literal ``None`` token parses back to ``target_id=None``.
    """
    entries: list[ReviewEntry] = []
    for line in text.splitlines():
        match = _ENTRY_RE.match(line.rstrip())
        if match is None:
            continue
        status, slug, raw_target, reason = match.groups()
        target_id = None if raw_target == "None" else raw_target
        entries.append(
            ReviewEntry(
                slug=slug,
                target_id=target_id,
                reason=reason,  # type: ignore[arg-type]  # regex alternation guarantees a valid ReviewReason
                status=status,  # type: ignore[arg-type]  # regex alternation guarantees a valid ReviewStatus
            )
        )
    return entries
