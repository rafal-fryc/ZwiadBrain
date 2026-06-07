"""Video-transcript helper for grounding a spoken quote against verbatim caption text.

A spoken quote in a hearing/floor video cannot be grounded against the video URL —
there is no fetchable text there.  The leg-history pipeline handles this in two ways,
in preference order (D72):

1. **Official transcript page** — the researcher sets the statement's ``source_url`` to a
   committee / GovInfo / clerk transcript page.  That is a normal web page, so the existing
   HTTP fetch resolves it and the unchanged D36 gate verbatim-matches the quote.  This module
   is NOT involved in that path; it is the high-yield path.

2. **YouTube captions (fallback)** — when only a video exists, the researcher may set
   ``source_url`` to the YouTube watch URL.  :func:`make_gate_fetch` wraps the gate's fetch so
   a YouTube URL resolves to its caption text via ``youtube-transcript-api`` (a declared
   dependency).  The D36 gate itself is unchanged — it just receives caption text instead of
   HTML.  Auto-generated captions lack punctuation/casing, so the case-sensitive verbatim gate
   USUALLY drops them (fail-closed by design, not a bug); prefer an official transcript.

Every failure mode here is fail-closed: a missing library, disabled/absent captions, or any
network/parse error degrades to ``(0, "")`` so the gate drops the quote and the video stays
Tier-2 :class:`~zwiadbrain.models.RelatedMedia` (a link, no quote) — it never crashes a render.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# YouTube video ids are 11 chars of [A-Za-z0-9_-]; pin the length so a trailing path
# segment or query value cannot be mistaken for an id.
_VIDEO_ID = r"([A-Za-z0-9_-]{11})"
_YOUTUBE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[?&]v=" + _VIDEO_ID),  # watch?v=ID (any param position)
    re.compile(r"youtu\.be/" + _VIDEO_ID),  # youtu.be/ID short link
    re.compile(r"/embed/" + _VIDEO_ID),  # /embed/ID
    re.compile(r"/v/" + _VIDEO_ID),  # /v/ID (legacy)
)


def youtube_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video id in *url*, or ``None`` if it is not a YouTube URL.

    Recognizes ``watch?v=``, ``youtu.be/``, ``/embed/``, and ``/v/`` forms on any YouTube
    host (``www.``/``m.``/bare).  A non-YouTube URL — e.g. an official transcript page —
    returns ``None`` so callers route it through normal HTTP instead of the caption path.
    """
    host_ok = bool(re.search(r"(?:^|//)(?:[\w-]+\.)*(?:youtube\.com|youtu\.be)/", url))
    if not host_ok:
        return None
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _youtube_captions(video_id: str, languages: tuple[str, ...]) -> str:
    """Fetch + concatenate caption text for *video_id* via ``youtube-transcript-api``.

    Imported locally so this module stays importable (and unrelated CLI commands stay
    fast) even when the optional ML/HTTP stack is absent; any failure propagates to
    :func:`fetch_captions`'s fail-closed boundary.
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415 (defer heavy import)

    fetched = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    return " ".join(snippet.text for snippet in fetched)


def fetch_captions(
    url: str,
    *,
    languages: tuple[str, ...] = ("en",),
    _fetcher: Callable[[str, tuple[str, ...]], str] | None = None,
) -> tuple[int, str]:
    """Resolve *url* to ``(status, caption_text)`` for the grounding gate.

    Returns ``(200, text)`` with whitespace collapsed when captions are retrieved, and
    ``(0, "")`` for a non-YouTube URL, missing captions, a missing library, or any other
    failure.  *_fetcher* injects the caption source for tests (default: the real API).
    """
    video_id = youtube_video_id(url)
    if video_id is None:
        return (0, "")
    fetcher = _fetcher if _fetcher is not None else _youtube_captions
    try:
        raw = fetcher(video_id, languages)
    except Exception:
        # Fail-closed boundary: a missing library, disabled/absent captions, or any
        # network/parse error must degrade the video to Tier-2 media (no quote) rather
        # than crash the render — mirrors _fetch_url's broad catch at the fetch boundary.
        return (0, "")
    text = " ".join(raw.split())
    return (200, text) if text else (0, "")


def make_gate_fetch(
    http_fetch: Callable[[str], tuple[int, str]],
    caption_fetch: Callable[[str], tuple[int, str]] = fetch_captions,
) -> Callable[[str], tuple[int, str]]:
    """Build the single-arg fetch the grounding gate expects, transcript-aware.

    A YouTube ``source_url`` resolves to caption text via *caption_fetch*; every other URL
    (official transcript pages, press pages, CREC) uses *http_fetch*.  The gate logic in
    :func:`~zwiadbrain.pipeline.leg_history.ground_items` is unchanged — it simply receives
    caption text for a video source_url.
    """

    def _fetch(url: str) -> tuple[int, str]:
        if youtube_video_id(url) is not None:
            return caption_fetch(url)
        return http_fetch(url)

    return _fetch
