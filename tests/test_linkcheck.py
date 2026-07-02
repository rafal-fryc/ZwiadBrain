"""Tests for the link-rot checker (D111 / check-links)."""

from zwiadbrain.pipeline.linkcheck import (
    DeadLink,
    check_pages,
    group_by_family,
    harvest_urls,
    url_family,
)


def test_harvest_urls_extracts_unique_urls_in_order() -> None:
    """should extract each http(s) url once, in first-seen order, trimming prose punctuation"""
    text = (
        "sources:\n  LegiScan: https://legiscan.com/IL/bill/HB2557/2019\n"
        "- [roll call](https://www.ilga.gov/legislation/votehistory/roll.pdf)\n"
        "See https://example.gov/page. And again https://legiscan.com/IL/bill/HB2557/2019\n"
    )
    assert harvest_urls(text) == [
        "https://legiscan.com/IL/bill/HB2557/2019",
        "https://www.ilga.gov/legislation/votehistory/roll.pdf",
        "https://example.gov/page",
    ]


def test_url_family_groups_by_host_and_first_segment() -> None:
    """should key a url by lowercased host plus its first path segment"""
    assert (
        url_family("https://WWW.ILGA.GOV/legislation/BillStatus.asp?DocNum=1")
        == "www.ilga.gov/legislation"
    )
    assert url_family("https://example.gov") == "example.gov"


def test_check_pages_reports_only_non_ok_urls_with_their_pages() -> None:
    """should return dead links with the pages they appear on; redirects count as alive"""
    pages = [
        ("il/a.md", "https://ok.gov/x https://dead.gov/y"),
        ("il/b.md", "https://dead.gov/y https://moved.gov/z"),
    ]
    statuses = {"https://ok.gov/x": 200, "https://dead.gov/y": 404, "https://moved.gov/z": 301}

    dead = check_pages(pages, fetch=lambda url: statuses[url])

    assert dead == [DeadLink(url="https://dead.gov/y", status=404, pages=("il/a.md", "il/b.md"))]


def test_check_pages_probes_each_unique_url_once() -> None:
    """should fetch a url appearing on many pages exactly once"""
    calls: list[str] = []

    def fetch(url: str) -> int:
        calls.append(url)
        return 404

    pages = [(f"p{i}.md", "https://dead.gov/family") for i in range(4)]
    dead = check_pages(pages, fetch=fetch)

    assert calls == ["https://dead.gov/family"]
    assert dead[0].pages == ("p0.md", "p1.md", "p2.md", "p3.md")


def test_group_by_family_clusters_a_retired_url_scheme() -> None:
    """should surface a site redesign as one large family ordered before isolated 404s"""
    ilga = "https://www.ilga.gov/legislation"
    dead = [
        DeadLink(url=f"{ilga}/BillStatus.asp?a=1", status=404, pages=("a",)),
        DeadLink(url=f"{ilga}/votehistory/x.pdf", status=404, pages=("a",)),
        DeadLink(url="https://leg.colorado.gov/content/hb24-1104vote", status=404, pages=("b",)),
        DeadLink(url=f"{ilga}/101/HB/10100HB2557.htm", status=404, pages=("c",)),
    ]

    families = group_by_family(dead)

    assert list(families) == ["www.ilga.gov/legislation", "leg.colorado.gov/content"]
    assert len(families["www.ilga.gov/legislation"]) == 3
