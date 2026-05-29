"""Tests for the derived SQLite index/watchlist (rebuilt from committed frontmatter)."""

import datetime as dt
from pathlib import Path

from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.store import Store


def _seed_wiki(wiki_root: Path) -> None:
    write_page(
        Bill(
            id="us-ca-sb-362",
            jurisdiction="US-CA",
            title="California Delete Act",
            bill_number="SB 362",
            status="enrolled",
            topics=["privacy", "data-brokers"],
        ),
        wiki_root,
    )
    write_page(
        Bill(
            id="118-hr-8818", jurisdiction="US", title="APRA", bill_number="HR 8818", tracking=False
        ),
        wiki_root,
    )
    write_page(
        EnforcementAction(
            id="ftc-betterhelp", jurisdiction="US", title="FTC v. BetterHelp", agency="FTC"
        ),
        wiki_root,
    )
    # A non-item Markdown file must be ignored by reindex.
    (wiki_root / "README.md").write_text("# Wiki\n", encoding="utf-8")


def test_reindex_builds_index_from_frontmatter(tmp_path: Path) -> None:
    """should index every committed page and record its relative path"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        assert store.reindex(wiki) == 3
        assert store.count() == 3
        row = store.get("us-ca-sb-362")
        assert row is not None
        assert row["bill_number"] == "SB 362"
        assert row["path"] == "states/ca/bills/us-ca-sb-362.md"


def test_reindex_is_rerunnable_without_duplicates(tmp_path: Path) -> None:
    """should rebuild cleanly so re-running does not duplicate rows"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        store.reindex(wiki)
        assert store.count() == 3


def test_tracked_excludes_untracked_items(tmp_path: Path) -> None:
    """should return only items with tracking=True from the watchlist"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        tracked_ids = {row["id"] for row in store.tracked()}
        assert "us-ca-sb-362" in tracked_ids
        assert "hr-8818" not in tracked_ids


def test_fts_search_matches_title_and_topics(tmp_path: Path) -> None:
    """should support lexical search over derived columns"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        assert "us-ca-sb-362" in store.search("Delete")
        assert "ftc-betterhelp" in store.search("BetterHelp")
        assert "us-ca-sb-362" in store.search("privacy")


def test_lawbrain_page_cache_upsert_and_fetch(tmp_path: Path) -> None:
    """should store and update law-brain page content hashes by slug"""
    with Store(tmp_path / "index.sqlite") as store:
        store.upsert_lawbrain_page("regulation-x", "hash1", dt.date(2026, 5, 6))
        store.upsert_lawbrain_page("regulation-x", "hash2", dt.date(2026, 5, 7))
        assert store.lawbrain_hashes() == {"regulation-x": "hash2"}


def test_corrupt_index_file_self_heals_on_open(tmp_path: Path) -> None:
    """should rebuild a corrupt (non-sqlite) index file instead of leaking a raw DatabaseError"""
    db_path = tmp_path / "index.sqlite"
    db_path.write_bytes(b"this is not a sqlite database header")
    with Store(db_path) as store:
        # the disposable index opened cleanly and is queryable from a fresh schema
        assert store.count() == 0
    # a real sqlite file now lives at the path
    header = db_path.read_bytes()[:16]
    assert header.startswith(b"SQLite format 3")
