import datetime as dt
from pathlib import Path

import httpx
import respx

from zwiadbrain.sources.enforcement.base import (
    EnforcementCandidate,
    extract_article_text,
    parse_feed,
)
from zwiadbrain.sources.enforcement.ftc import FTCSource
from zwiadbrain.sources.enforcement.state_ag import StateAGSource

_FIX = Path(__file__).parent / "fixtures" / "enforcement"
_RSS_URL = "https://www.ftc.gov/feeds/press-release.xml"


def test_parse_feed_extracts_entries() -> None:
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>FTC sues Acme</title><link>https://www.ftc.gov/a</link>
        <description>data security</description>
        <pubDate>Thu, 02 Jan 2025 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    entries = parse_feed(xml)
    assert entries[0]["title"] == "FTC sues Acme"
    assert entries[0]["link"] == "https://www.ftc.gov/a"
    published = entries[0]["published"]
    assert isinstance(published, dt.date)
    assert published.isoformat() == "2025-01-02"


def test_extract_article_text_strips_script_and_nav() -> None:
    html = """<html><head><style>x{}</style></head><body>
      <nav>menu</nav><main><p>The FTC alleged Acme failed to secure data.</p>
      <script>tracker()</script></main></body></html>"""
    text = extract_article_text(html)
    assert "FTC alleged Acme" in text
    assert "tracker()" not in text
    assert "menu" not in text


def test_candidate_defaults() -> None:
    c = EnforcementCandidate(source="ftc", agency="FTC", agency_slug="ftc",
                             jurisdiction="US", title="t", url="https://x")
    assert c.text is None and c.published is None


@respx.mock
def test_ftc_discover_maps_candidates() -> None:
    respx.get(_RSS_URL).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text())
    )
    source = FTCSource(_RSS_URL)
    cands = source.discover(limit=10)
    assert cands[0].agency_slug == "ftc" and cands[0].jurisdiction == "US"
    assert cands[0].title.startswith("FTC Takes Action Against Acme")
    assert cands[0].published is not None and cands[0].published.year == 2025


@respx.mock
def test_ftc_discover_forward_from_now_window() -> None:
    respx.get(_RSS_URL).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text())
    )
    source = FTCSource(_RSS_URL)
    cands = source.discover(since=dt.datetime(2025, 2, 1), limit=10)
    assert [c.published.month for c in cands if c.published is not None] == [3]


@respx.mock
def test_ftc_fetch_text_extracts_body() -> None:
    url = "https://www.ftc.gov/news/press-releases/2025/01/acme"
    html = (_FIX / "ftc_press.html").read_text()
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    source = FTCSource(_RSS_URL)
    cand = EnforcementCandidate(source="ftc", agency="FTC", agency_slug="ftc",
                                jurisdiction="US", title="t", url=url)
    text = source.fetch_text(cand)
    assert "Acme, Inc. failed to implement reasonable data security" in text
    assert "File No. 2023155" in text
    assert "analytics()" not in text


@respx.mock
def test_state_ag_rss_discover() -> None:
    url = "https://oag.ca.gov/news/press-releases/feed"
    respx.get(url).mock(return_value=httpx.Response(200, text=(_FIX / "ag_ca_rss.xml").read_text()))
    source = StateAGSource(name="California OAG", agency_slug="ca-oag",
                           jurisdiction="US-CA", url=url, kind="rss")
    cands = source.discover(limit=10)
    assert cands[0].agency == "California OAG" and cands[0].jurisdiction == "US-CA"
    assert "DoorDash" in cands[0].title


@respx.mock
def test_state_ag_html_discover_uses_item_selector() -> None:
    url = "https://oag.example/news"
    html_text = (_FIX / "ag_html_list.html").read_text()
    respx.get(url).mock(return_value=httpx.Response(200, text=html_text))
    source = StateAGSource(name="Example OAG", agency_slug="ex-oag", jurisdiction="US-XX",
                           url=url, kind="html", item_selector="li.press-item a")
    cands = source.discover(limit=10)
    titles = [c.title for c in cands]
    assert "AG Sues Sephora Over Data Broker Violations" in titles
    assert cands[0].url.startswith("https://oag.example/news/2025/sephora")


@respx.mock
def test_state_ag_discover_failure_is_isolated() -> None:
    url = "https://oag.broken/news"
    respx.get(url).mock(return_value=httpx.Response(500))
    source = StateAGSource(name="Broken OAG", agency_slug="bk-oag", jurisdiction="US-XX",
                           url=url, kind="html", item_selector="a")
    assert source.discover(limit=10) == []


def test_enforcement_sources_send_browser_user_agent() -> None:
    from zwiadbrain.sources.enforcement.ftc import FTCSource
    from zwiadbrain.sources.enforcement.state_ag import StateAGSource
    ftc = FTCSource()
    ag = StateAGSource(name="X", agency_slug="x-oag", jurisdiction="US-XX",
                       url="https://example.gov/feed", kind="rss")
    assert "Mozilla" in ftc.client.headers.get("user-agent", "")
    assert "Mozilla" in ag.client.headers.get("user-agent", "")
