"""Pure jurisdiction-scoped shortlist + shared-key grounding confirm for law-brain
commentary matching.

Nothing here does I/O (mirrors :mod:`zwiadbrain.pipeline.enforcement`). The CLI fetch
half composes :func:`build_shortlist` to hand the ``lawbrain-matcher`` subagent a small,
same-jurisdiction candidate set instead of the full tracked corpus; the render half
composes :func:`confirm_match` as the deterministic trust boundary that grounds every
LLM-proposed link (D16). When ``require_shared_key`` is on, a purely *topical* match —
high confidence but no shared jurisdiction-qualified identifier — never auto-applies; it
falls to the review queue as ``weak-grounding``. An operator ``override`` recorded in
``links.yaml`` bypasses the shared-key gate but never the confidence floor.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from zwiadbrain.pipeline.lawbrain_keys import normalize_jurisdiction
from zwiadbrain.sources.lawbrain import LawBrainPage

# Tokens dropped before tag/keyword overlap scoring (corpus noise / structural words),
# so two single-subject pages compare on their substantive terms, not boilerplate.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "of", "a", "an", "for", "to", "in", "on",
        "act", "bill", "ai", "law", "rule", "regulation",
    }
)


class TargetRef(BaseModel):
    """A lightweight reference to a tracked ZwiadBrain item (a shortlist candidate).

    ``keys`` are the item's jurisdiction-qualified keys (from
    :func:`zwiadbrain.pipeline.lawbrain_keys.tracked_item_keys`); ``confirm_match``
    intersects them with the page's keys to ground an LLM proposal.
    """

    id: str
    kind: Literal["bill", "enforcement"]
    jurisdiction: str
    title: str
    keys: list[str]


def _tokens(text: str) -> frozenset[str]:
    """Lowercase, split on non-word runs, drop stopwords."""
    raw = text.lower().replace("-", " ").replace(":", " ").replace(".", " ")
    return frozenset(t for t in re.split(r"\s+", raw) if t and t not in _STOPWORDS)


def _overlap(page: LawBrainPage, target: TargetRef) -> int:
    """Count of shared significant tokens between the page (tags + title) and the
    target (title). A coarse topical ranking signal — not a confirmation."""
    page_tokens = _tokens(" ".join(page.tags) + " " + page.title)
    target_tokens = _tokens(target.title)
    return len(page_tokens & target_tokens)


def build_shortlist(page: LawBrainPage, targets: list[TargetRef]) -> list[TargetRef]:
    """Candidate tracked items for the ``lawbrain-matcher`` subagent: those sharing the
    page's normalized jurisdiction, ranked by descending tag/keyword overlap.

    Jurisdiction is the hard filter (``US-Federal`` normalizes to ``US`` to match
    ZwiadBrain's federal targets); never returns the full corpus.
    """
    page_jurisdictions = {normalize_jurisdiction(j) for j in page.jurisdiction}
    in_scope = [
        t for t in targets if normalize_jurisdiction(t.jurisdiction) in page_jurisdictions
    ]
    return sorted(in_scope, key=lambda t: (-_overlap(page, t), t.id))


def confirm_match(
    *,
    page_keys: set[str],
    target_keys: set[str],
    confidence: float,
    min_confidence: float,
    require_shared_key: bool,
    override: bool = False,
) -> bool:
    """Deterministic grounding of an LLM-proposed link (D16).

    Confidence must clear the floor first; then the shared-key gate is satisfied when an
    operator ``override`` is recorded, OR the deployment does not require a shared key,
    OR the page and target share at least one jurisdiction-qualified key. An ``override``
    bypasses the shared-key gate but never the confidence floor.
    """
    if confidence < min_confidence:
        return False
    return override or not require_shared_key or len(page_keys & target_keys) >= 1
