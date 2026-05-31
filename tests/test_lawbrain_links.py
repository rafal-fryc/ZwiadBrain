from zwiadbrain.models import CommentaryLink
from zwiadbrain.pipeline.lawbrain_links import harvest_links

_DENYLIST = [
    ".gov",
    "legiscan.com",
    "courtlistener.com",
    "wikipedia.org",
    "europa.eu",
    "legislation.gov.uk",
]

# A mini memo mixing primary-source links (dropped) and law-firm/secondary links (kept).
_MEMO = """\
## Sources

- [California CPPA enforcement order](https://cppa.ca.gov/announcements/order.pdf)
- [Bill text on LegiScan](https://legiscan.com/CA/text/SB53)
- [Mayer Brown client alert](https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert)
- [The National Law Review analysis](https://natlawreview.com/article/cppa-onstar)
- Bare reference: https://www.jdsupra.com/legalnews/cppa-settlement-12345/
- Primary statute: https://leginfo.legislature.ca.gov/faces/billText.xhtml
- Background: https://en.wikipedia.org/wiki/California_Consumer_Privacy_Act
"""

_PAGE_BODY = """\
## Summary

The CPPA settled with GM/OnStar. See the [Mayer Brown client alert](https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert)
and the agency's own [order](https://cppa.ca.gov/announcements/order.pdf).

Further commentary: https://iapp.org/news/a/cppa-onstar-takeaways/
"""


def test_harvest_links_extracts_markdown_links_from_page_body() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[],
        primary_source_domains=_DENYLIST,
    )
    assert CommentaryLink(
        text="Mayer Brown client alert",
        url="https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert",
    ) in links


def test_harvest_links_preserves_anchor_text() -> None:
    links = harvest_links(
        page_body="",
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    by_url = {link.url: link.text for link in links}
    assert (
        by_url["https://natlawreview.com/article/cppa-onstar"]
        == "The National Law Review analysis"
    )


def test_harvest_links_bare_url_anchor_is_host() -> None:
    links = harvest_links(
        page_body="See https://iapp.org/news/a/cppa-onstar-takeaways/ for more.",
        memo_texts=[],
        primary_source_domains=_DENYLIST,
    )
    assert links == [
        CommentaryLink(text="iapp.org", url="https://iapp.org/news/a/cppa-onstar-takeaways/"),
    ]


def test_harvest_links_drops_primary_source_domains() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    hosts = {link.url for link in links}
    # .gov, legiscan.com, wikipedia.org, leginfo.legislature.ca.gov (.gov) all dropped.
    assert "https://cppa.ca.gov/announcements/order.pdf" not in hosts
    assert "https://legiscan.com/CA/text/SB53" not in hosts
    assert "https://en.wikipedia.org/wiki/California_Consumer_Privacy_Act" not in hosts
    assert "https://leginfo.legislature.ca.gov/faces/billText.xhtml" not in hosts
    # Law-firm / secondary commentary kept.
    assert "https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert" in hosts
    assert "https://natlawreview.com/article/cppa-onstar" in hosts
    assert "https://www.jdsupra.com/legalnews/cppa-settlement-12345/" in hosts
    assert "https://iapp.org/news/a/cppa-onstar-takeaways/" in hosts


def test_harvest_links_dedups_across_page_and_memo() -> None:
    # The Mayer Brown alert appears in BOTH the page body and the memo -> one entry.
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    mayer = [link for link in links if link.url.startswith("https://www.mayerbrown.com")]
    assert len(mayer) == 1


def test_harvest_links_dedups_trailing_slash_and_host_case() -> None:
    links = harvest_links(
        page_body="[A](https://Example.com/path/) and [B](https://example.com/path)",
        memo_texts=[],
        primary_source_domains=[],
    )
    assert len(links) == 1


def test_harvest_links_stable_sort_by_host_then_url() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    keyed = [(link.url.split("/")[2].lower(), link.url) for link in links]
    assert keyed == sorted(keyed)


def test_harvest_links_empty_when_no_links() -> None:
    assert harvest_links(
        page_body="A page body with no links at all.",
        memo_texts=["Memo with no links."],
        primary_source_domains=_DENYLIST,
    ) == []


def test_harvest_links_markdown_link_not_double_counted_as_bare_url() -> None:
    # A URL already inside a [text](url) link must not ALSO appear as a bare-url anchor.
    links = harvest_links(
        page_body="[IAPP](https://iapp.org/news/a/x/)",
        memo_texts=[],
        primary_source_domains=[],
    )
    assert links == [
        CommentaryLink(text="IAPP", url="https://iapp.org/news/a/x/"),
    ]


def test_harvest_links_bare_url_with_query_string() -> None:
    links = harvest_links(
        page_body="details at https://example.com/search?q=foo&bar=1",
        memo_texts=[], primary_source_domains=[],
    )
    assert links[0].url == "https://example.com/search?q=foo&bar=1"


def test_harvest_links_strips_trailing_period_from_bare_url() -> None:
    links = harvest_links(
        page_body="See https://example.com/article. More text.",
        memo_texts=[], primary_source_domains=[],
    )
    assert links[0].url == "https://example.com/article"
