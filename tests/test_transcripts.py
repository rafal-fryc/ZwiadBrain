"""Tests for the video-transcript helper (sources/transcripts.py).

All tests are offline: the caption fetcher is dependency-injected, so nothing here
imports ``youtube_transcript_api`` or touches the network.  The real caption path is
exercised only by live UAT (and is expected to fail-closed on auto-captions, by design).
"""

from __future__ import annotations

from zwiadbrain.sources.transcripts import (
    fetch_captions,
    make_gate_fetch,
    memoize_fetch,
    youtube_video_id,
)

# ---------------------------------------------------------------------------
# youtube_video_id — URL parsing (deterministic, offline)
# ---------------------------------------------------------------------------


def test_youtube_video_id_parses_watch_url() -> None:
    """should extract the id from a standard watch?v= URL"""
    assert youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_video_id_parses_watch_url_with_extra_params() -> None:
    """should extract the id when other query params surround v="""
    url = "https://www.youtube.com/watch?list=PL123&v=dQw4w9WgXcQ&t=42s"
    assert youtube_video_id(url) == "dQw4w9WgXcQ"


def test_youtube_video_id_parses_short_youtu_be_url() -> None:
    """should extract the id from a youtu.be short link"""
    assert youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=10") == "dQw4w9WgXcQ"


def test_youtube_video_id_parses_embed_url() -> None:
    """should extract the id from an /embed/ URL"""
    assert youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_video_id_parses_m_dot_watch_url() -> None:
    """should extract the id from the mobile m.youtube.com host"""
    assert youtube_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_video_id_returns_none_for_non_youtube() -> None:
    """should return None for a non-YouTube URL (e.g. an official transcript page)"""
    assert youtube_video_id("https://www.congress.gov/crec/2024/02/05") is None


def test_youtube_video_id_returns_none_for_watch_without_v() -> None:
    """should return None for a youtube URL lacking a v= id"""
    assert youtube_video_id("https://www.youtube.com/results?search_query=ai") is None


# ---------------------------------------------------------------------------
# fetch_captions — fail-closed boundary (dependency-injected)
# ---------------------------------------------------------------------------


def test_fetch_captions_returns_zero_for_non_youtube_url() -> None:
    """should return (0, '') for a non-YouTube URL without calling the fetcher"""
    assert fetch_captions("https://example.gov/transcript") == (0, "")


def test_fetch_captions_returns_text_on_success() -> None:
    """should return (200, normalized text) when the injected fetcher yields captions"""
    def fake(_video_id: str, _languages: tuple[str, ...]) -> str:
        return "We must   protect\nconsumers."

    status, text = fetch_captions(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", _fetcher=fake
    )
    assert status == 200
    assert text == "We must protect consumers."  # whitespace collapsed


def test_fetch_captions_fails_closed_on_fetcher_exception() -> None:
    """should return (0, '') when the fetcher raises (no captions / disabled / network)"""
    def boom(_video_id: str, _languages: tuple[str, ...]) -> str:
        raise RuntimeError("TranscriptsDisabled")

    assert fetch_captions(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", _fetcher=boom
    ) == (0, "")


def test_fetch_captions_fails_closed_on_empty_text() -> None:
    """should return (0, '') when the fetcher yields only whitespace"""
    def empty(_video_id: str, _languages: tuple[str, ...]) -> str:
        return "   \n  "

    assert fetch_captions(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", _fetcher=empty
    ) == (0, "")


# ---------------------------------------------------------------------------
# make_gate_fetch — routes YouTube URLs to captions, else to http_fetch
# ---------------------------------------------------------------------------


def test_make_gate_fetch_routes_youtube_to_caption_fetch() -> None:
    """should call caption_fetch for a YouTube URL and never touch http_fetch"""
    calls: list[tuple[str, str]] = []

    def http_fetch(url: str) -> tuple[int, str]:
        calls.append(("http", url))
        return (200, "html")

    def caption_fetch(url: str) -> tuple[int, str]:
        calls.append(("caption", url))
        return (200, "caption text")

    gate_fetch = make_gate_fetch(http_fetch, caption_fetch=caption_fetch)
    status, text = gate_fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert (status, text) == (200, "caption text")
    assert all(kind == "caption" for kind, _ in calls)


def test_make_gate_fetch_routes_non_youtube_to_http_fetch() -> None:
    """should call http_fetch for a non-YouTube URL (official transcript / press page)"""
    def http_fetch(_url: str) -> tuple[int, str]:
        return (200, "<html>official transcript</html>")

    def caption_fetch(_url: str) -> tuple[int, str]:
        raise AssertionError("caption_fetch must not be called for a non-YouTube URL")

    gate_fetch = make_gate_fetch(http_fetch, caption_fetch=caption_fetch)
    result = gate_fetch("https://www.congress.gov/crec/x")
    assert result == (200, "<html>official transcript</html>")


# ---------------------------------------------------------------------------
# memoize_fetch — per-run fetch cache (PHASE-20)
# ---------------------------------------------------------------------------


def test_memoize_fetch_calls_inner_once_per_url() -> None:
    """should fetch a repeated url only once and serve the cached result thereafter"""
    calls: list[str] = []

    def inner(url: str) -> tuple[int, str]:
        calls.append(url)
        return (200, f"body for {url}")

    fetch = memoize_fetch(inner)
    first = fetch("https://a.test/x")
    second = fetch("https://a.test/x")

    assert calls == ["https://a.test/x"]  # inner hit exactly once
    assert first == second == (200, "body for https://a.test/x")


def test_memoize_fetch_fetches_each_distinct_url() -> None:
    """should call inner once per DISTINCT url"""
    calls: list[str] = []

    def inner(url: str) -> tuple[int, str]:
        calls.append(url)
        return (200, url)

    fetch = memoize_fetch(inner)
    fetch("https://a.test/1")
    fetch("https://a.test/2")
    fetch("https://a.test/1")

    assert calls == ["https://a.test/1", "https://a.test/2"]


def test_memoize_fetch_instances_have_independent_caches() -> None:
    """each wrapper is run-scoped: two wrappers do not share a cache"""
    calls: list[str] = []

    def inner(url: str) -> tuple[int, str]:
        calls.append(url)
        return (200, "x")

    fetch_a = memoize_fetch(inner)
    fetch_b = memoize_fetch(inner)
    fetch_a("https://a.test/x")
    fetch_b("https://a.test/x")

    assert calls == ["https://a.test/x", "https://a.test/x"]  # not shared


def test_memoize_fetch_caches_error_tuple_too() -> None:
    """a (0, '') failure is cached like any other result — one attempt per url per run"""
    calls: list[str] = []

    def inner(url: str) -> tuple[int, str]:
        calls.append(url)
        return (0, "")

    fetch = memoize_fetch(inner)
    assert fetch("https://down.test/x") == (0, "")
    assert fetch("https://down.test/x") == (0, "")
    assert calls == ["https://down.test/x"]
