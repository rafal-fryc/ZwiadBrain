"""Pure copy/merge/staleness helpers for law-brain commentary consolidation.

Nothing here does I/O. The render half composes these with the renderer to fold a
matched law-brain page into an existing tracked page's ``commentary_sources``
idempotently, and to surface pages that have vanished from the law brain.

The idempotency contract mirrors :func:`zwiadbrain.pipeline.enforcement.merge_developments`:
re-seeing the same slug at the same ``content_hash`` returns the existing list
unchanged (same object identity), so a repeated sync produces a byte-identical render
and a clean ``git status`` (D20). A body bump (new ``content_hash``) replaces only that
one block; a new slug appends. The result is always slug-sorted so the renderer's output
is deterministic regardless of merge order.

The stored ``body`` is the **raw** law-brain markdown (verbatim); the render-time
transforms (``_demote_headings`` + ``_neutralize_wikilinks``) are applied in
``templates._commentary_block``, keeping ``content_hash`` tied to the source bytes (D58).
"""

from __future__ import annotations

from typing import Literal

from zwiadbrain.models import CommentaryLink, CommentarySource
from zwiadbrain.sources.lawbrain import LawBrainPage


def build_commentary_source(
    *,
    page: LawBrainPage,
    matched_by: Literal["deterministic", "llm"],
    confidence: float,
    links: list[CommentaryLink],
) -> CommentarySource:
    """Build a :class:`CommentarySource` from a matched law-brain page.

    ``body`` is the raw page body (verbatim — render-time transforms are applied
    later in ``templates._commentary_block``); ``content_hash`` and ``updated`` are
    carried from the page so staleness detection compares against the source bytes,
    not display metadata. ``path`` and ``slug`` both come from ``page.slug`` (the
    law-brain page is addressed by slug; there is no separate file-path key).
    """
    return CommentarySource(
        path=page.slug,
        slug=page.slug,
        updated=page.updated,
        content_hash=page.content_hash,
        matched_by=matched_by,
        confidence=confidence,
        body=page.body,
        links=links,
    )


def merge_commentary(
    existing: list[CommentarySource],
    new: CommentarySource,
) -> list[CommentarySource]:
    """Fold *new* into *existing*, deduped by slug, returned slug-sorted.

    Three cases:

    * **same slug + unchanged ``content_hash``** — the existing list is returned
      unchanged (same object identity); a repeated sync is a no-op and leaves
      ``git status`` clean (D20). Mirrors :func:`~enforcement.merge_developments`.
    * **same slug + changed ``content_hash``** — replace that one block only;
      all other entries are preserved as-is.
    * **new slug** — append; then sort.

    The result is always sorted by slug so the renderer emits a deterministic,
    byte-identical block order regardless of the order pages were merged.
    """
    for current in existing:
        if current.slug == new.slug:
            if current.content_hash == new.content_hash:
                # No-op: return the existing list unchanged so the renderer
                # produces byte-identical output (D20).
                return existing
            replaced = [new if s.slug == new.slug else s for s in existing]
            return sorted(replaced, key=lambda s: s.slug)
    combined = [*existing, new]
    return sorted(combined, key=lambda s: s.slug)


def detect_stale(
    existing: list[CommentarySource],
    live_slugs: set[str],
) -> list[str]:
    """Return the slugs of existing commentary whose source page has vanished.

    Slugs present in *existing* but absent from *live_slugs* — i.e. law-brain
    pages whose committed commentary no longer has a live source. The render half
    emits a ``stale`` review note for these rather than silently dropping the
    analysis. Result is slug-sorted for deterministic, byte-identical review output.
    """
    return sorted(s.slug for s in existing if s.slug not in live_slugs)
