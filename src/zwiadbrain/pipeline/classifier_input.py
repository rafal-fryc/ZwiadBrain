"""Stage classifier input: batch bills and repair thin or oversized summaries (D118).

The classifier judges scope from a bill's title and official summary only. Two shapes
defeat that: a *thin* summary that merely repeats the title (LegiScan descriptions for
many 2026 bills — the classifier had nothing to judge), and an *oversized* summary (omnibus
CRS summaries past the subagent's context budget, previously hand-staged as ``mega_*.json``).
Both are repaired here, deterministically, with seed-hit snippets: from the enacted text for
a thin summary, from the summary itself for an oversized one. What could not be repaired is
labelled so the classifier flags it for review instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from zwiadbrain.models import Bill
from zwiadbrain.pipeline.extract import select_bill_document

# Summaries longer than this are cut to a head + snippets (~20k chars ≈ 5k tokens, which
# keeps a 15-bill batch well inside one subagent's context).
_OVERSIZED_CHARS = 20_000
# A summary adding fewer than this many characters to the title says nothing new.
_THIN_EXTRA_CHARS = 40
# Shorter than this, a summary is a title paraphrase ("An act ... relating to crimes.").
_MIN_SUMMARY_CHARS = 150
_SNIPPET_RADIUS = 300
_MAX_SNIPPETS = 10
_OPENING_CHARS = 3_000

_NON_WORD = re.compile(r"[\W_]+")

# One bill's classifier input, serialized to a batch JSON file.
ClassifierItem = dict[str, str | list[str]]


def _normalize(text: str) -> str:
    return _NON_WORD.sub(" ", text.lower()).strip()


def is_thin_summary(title: str, summary: str | None) -> bool:
    """True when the summary is missing or adds nothing substantive to the title."""
    if not summary or len(summary.strip()) < _MIN_SUMMARY_CHARS:
        return True
    norm_title, norm_summary = _normalize(title), _normalize(summary)
    if not norm_summary or norm_summary == norm_title:
        return True
    if norm_summary.startswith(norm_title) or norm_title.startswith(norm_summary):
        return len(norm_summary) - len(norm_title) < _THIN_EXTRA_CHARS
    return False


def seed_snippets(
    text: str,
    seeds: list[str],
    *,
    radius: int = _SNIPPET_RADIUS,
    max_snippets: int = _MAX_SNIPPETS,
) -> list[str]:
    """Context windows around case-insensitive seed hits, merged where they overlap.

    Each snippet is prefixed with the first seed it contains, e.g. ``[personal data] ...``.
    """
    lowered = text.lower()
    hits: list[tuple[int, int, str]] = []
    for seed in seeds:
        needle = seed.lower()
        start = lowered.find(needle)
        while start != -1:
            hits.append((start, start + len(needle), seed))
            start = lowered.find(needle, start + len(needle))
    hits.sort()
    windows: list[tuple[int, int, str]] = []  # (start, end, first seed in the window)
    for start, end, seed in hits:
        lo, hi = max(0, start - radius), min(len(text), end + radius)
        if windows and lo <= windows[-1][1]:
            prev_lo, prev_hi, prev_seed = windows[-1]
            windows[-1] = (prev_lo, max(prev_hi, hi), prev_seed)
        else:
            windows.append((lo, hi, seed))
    return [
        f"[{seed}] {' '.join(text[lo:hi].split())}" for lo, hi, seed in windows[:max_snippets]
    ]


def classifier_item(
    bill: Bill,
    seeds: list[str],
    fetch_text: Callable[[str], str],
    *,
    oversized_chars: int = _OVERSIZED_CHARS,
) -> ClassifierItem:
    """One bill's classifier input: ``{id, title, summary}`` plus any repair.

    ``fetch_text`` turns a text-version URL into plain text (``""`` on failure); it is called
    only for thin summaries. Adds ``text_snippets`` / ``summary_snippets`` and an
    ``input_note`` explaining what the classifier is looking at.
    """
    summary = bill.summary or ""
    item: ClassifierItem = {"id": bill.id, "title": bill.title, "summary": summary}
    if len(summary) > oversized_chars:
        head_chars = oversized_chars // 4
        item["summary"] = summary[:head_chars]
        item["summary_snippets"] = seed_snippets(summary, seeds)
        item["input_note"] = (
            f"Summary oversized ({len(summary):,} chars): first {head_chars:,} chars kept, "
            "plus seed-hit snippets from the full summary. Judge each snippet as a possible "
            "discrete operative provision (omnibus rider rule)."
        )
        return item
    if not is_thin_summary(bill.title, bill.summary):
        return item
    document = select_bill_document(bill)
    text = fetch_text(document.url) if document is not None and document.url else ""
    if not text.strip() or document is None:
        item["input_note"] = (
            "THIN-SUMMARY: the official summary repeats the title and no bill text could be "
            "fetched. Mark confidence low and start the rationale with REVIEW."
        )
        return item
    snippets = seed_snippets(text, seeds) or [
        f"[opening] {' '.join(text[:_OPENING_CHARS].split())}"
    ]
    item["text_snippets"] = snippets
    item["input_note"] = (
        f"The official summary repeats the title; snippets are from the {document.code} "
        "bill text. Judge scope from the snippets."
    )
    return item


def batch_items(items: list[ClassifierItem], size: int) -> list[list[ClassifierItem]]:
    """Split classifier items into consecutive batches of at most ``size``."""
    return [items[n : n + size] for n in range(0, len(items), size)]
