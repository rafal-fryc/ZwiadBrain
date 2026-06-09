"""Tests for the derived SQLite index/watchlist (rebuilt from committed frontmatter)."""

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from zwiadbrain.exceptions import StoreError
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


def test_indexing_same_id_twice_yields_one_fts_row(tmp_path: Path) -> None:
    """should not leave a stale duplicate FTS row when an item is re-indexed in place"""
    with Store(tmp_path / "index.sqlite") as store:
        bill = Bill(
            id="us-ca-sb-362",
            jurisdiction="US-CA",
            title="California Delete Act",
            bill_number="SB 362",
        )
        store._index_item(bill, "states/ca/bills/us-ca-sb-362.md")  # pyright: ignore[reportPrivateUsage]
        store._index_item(bill, "states/ca/bills/us-ca-sb-362.md")  # pyright: ignore[reportPrivateUsage]
        row = store.conn.execute(
            "SELECT COUNT(*) FROM items_fts WHERE id = ?", ("us-ca-sb-362",)
        ).fetchone()
        assert int(row[0]) == 1
        # and the row is still findable
        assert "us-ca-sb-362" in store.search("Delete")


def test_search_returns_empty_on_fts_metacharacter_query_instead_of_raising(tmp_path: Path) -> None:
    """should not raise OperationalError when a query contains unbalanced FTS metacharacters"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        # an unbalanced quote is a malformed FTS5 query — must degrade to [] not crash
        assert store.search('"unterminated') == []
        # a normal query still works after the failed one (connection not poisoned)
        assert "us-ca-sb-362" in store.search("Delete")


def test_reindex_rolls_back_on_mid_loop_failure(tmp_path: Path) -> None:
    """should leave the prior index intact when a write fails partway through a rebuild"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        assert store.count() == 3

        # Force a failure on the third _index_item call of the next rebuild.
        calls = {"n": 0}
        original = store._index_item  # pyright: ignore[reportPrivateUsage]

        def exploding(item: object, rel_path: str, *, extracted_text: str = "") -> None:
            calls["n"] += 1
            if calls["n"] == 3:
                raise sqlite3.OperationalError("disk I/O error")
            original(item, rel_path, extracted_text=extracted_text)  # type: ignore[arg-type]

        store._index_item = exploding  # type: ignore[assignment, method-assign]
        with pytest.raises(StoreError):
            store.reindex(wiki)
        # restore so the context-manager close path is unaffected
        store._index_item = original  # type: ignore[method-assign]

    # A brand-new connection sees the committed, pre-failure index — not a half-rebuilt one.
    with Store(tmp_path / "index.sqlite") as store2:
        assert store2.count() == 3


# ---------------------------------------------------------------------------
# Extracted-text sidecar indexing + schema-version migration (PR-B)
# ---------------------------------------------------------------------------


def test_reindex_indexes_sidecar_text_for_search(tmp_path: Path) -> None:
    """should make a page findable by a phrase that appears only in its .text.md sidecar"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    page = wiki / "states" / "ca" / "bills" / "us-ca-sb-362.md"
    page.with_name("us-ca-sb-362.text.md").write_text(
        "# Extracted text\n\nA covered business shall register as a frontier developer.\n",
        encoding="utf-8",
    )
    with Store(tmp_path / "index.sqlite") as store:
        assert store.reindex(wiki) == 3  # the sidecar itself is not an indexed page
        assert store.search("frontier developer") == ["us-ca-sb-362"]


def test_reindex_without_sidecar_indexes_empty_text(tmp_path: Path) -> None:
    """should index no extracted text (search miss) when a page has no sidecar"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(tmp_path / "index.sqlite") as store:
        store.reindex(wiki)
        assert store.search("frontier developer") == []


def test_outdated_schema_version_migrates_keeping_lawbrain_cache(tmp_path: Path) -> None:
    """should drop+recreate the derived tables on a version mismatch but keep lawbrain_pages"""
    db_path = tmp_path / "index.sqlite"
    # Pre-create a v1-shaped database: old items_fts without extracted_text, user_version 0,
    # plus a lawbrain_pages row that must survive the migration.
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE items (id TEXT PRIMARY KEY, type TEXT NOT NULL);
        CREATE VIRTUAL TABLE items_fts USING fts5(
            id UNINDEXED, title, jurisdiction, status, bill_number, topics, agency, docket
        );
        CREATE TABLE lawbrain_pages (
            slug TEXT PRIMARY KEY, content_hash TEXT NOT NULL, updated TEXT, last_seen TEXT
        );
        INSERT INTO lawbrain_pages VALUES ('regulation-x', 'hash1', NULL, NULL);
        """
    )
    conn.commit()
    conn.close()

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(db_path) as store:
        # opens cleanly, the v2 schema is queryable, and extracted-text search works
        store.reindex(wiki)
        page = wiki / "states" / "ca" / "bills" / "us-ca-sb-362.md"
        page.with_name("us-ca-sb-362.text.md").write_text("frontier developer", encoding="utf-8")
        store.reindex(wiki)
        assert store.search("frontier developer") == ["us-ca-sb-362"]
        # the law-brain sync cache survived the migration
        assert store.lawbrain_hashes() == {"regulation-x": "hash1"}


def test_current_schema_version_is_not_remigrated(tmp_path: Path) -> None:
    """should keep indexed rows across reopens once the schema version matches"""
    db_path = tmp_path / "index.sqlite"
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    _seed_wiki(wiki)
    with Store(db_path) as store:
        store.reindex(wiki)
    with Store(db_path) as store2:
        # a reopen at the current version must not drop the derived tables
        assert store2.count() == 3
