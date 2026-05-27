"""Derived SQLite index, watchlist, and law-brain page cache.

The committed wiki frontmatter is the source of truth; this index is a derived,
gitignored cache rebuilt from ``wiki/**/*.md`` by :meth:`Store.reindex`. It also
doubles as the watchlist (``tracking`` flag) and holds the ``lawbrain_pages``
content-hash cache used to detect changed law-brain pages.

Retrieval is lexical only (SQLite FTS5/BM25 over derived columns) — no
embeddings (decision 13).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from types import TracebackType

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.wiki.schema import from_page

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT,
    bill_number TEXT,
    agency      TEXT,
    docket      TEXT,
    enacted     INTEGER NOT NULL DEFAULT 0,
    public_law  TEXT,
    tracking    INTEGER NOT NULL DEFAULT 1,
    change_hash TEXT,
    update_date TEXT,
    topics      TEXT NOT NULL DEFAULT '[]',
    path        TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    id UNINDEXED, title, jurisdiction, status, bill_number, topics, agency, docket
);
CREATE TABLE IF NOT EXISTS lawbrain_pages (
    slug         TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    updated      TEXT,
    last_seen    TEXT
);
"""


class Store:
    """A connection to the derived SQLite index."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # --- indexing -------------------------------------------------------

    def reindex(self, wiki_root: Path) -> int:
        """Rebuild the index from every committed page under ``wiki_root``.

        Non-item Markdown (e.g. ``README.md``) is skipped. Returns the number of
        indexed pages.
        """
        self.conn.execute("DELETE FROM items")
        self.conn.execute("DELETE FROM items_fts")
        count = 0
        for path in sorted(wiki_root.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            try:
                item = from_page(text)
            except WikiSchemaError:
                continue  # not a tracked-item page (README, index, etc.)
            self._index_item(item, path.relative_to(wiki_root).as_posix())
            count += 1
        self.conn.commit()
        return count

    def _index_item(self, item: Bill | EnforcementAction, rel_path: str) -> None:
        is_bill = isinstance(item, Bill)
        bill_number = item.bill_number if isinstance(item, Bill) else None
        enacted = int(item.enacted) if isinstance(item, Bill) else 0
        public_law = item.public_law if isinstance(item, Bill) else None
        change_hash = item.change_hash if isinstance(item, Bill) else None
        update_date = item.update_date if isinstance(item, Bill) else None
        agency = item.agency if isinstance(item, EnforcementAction) else None
        docket = item.docket if isinstance(item, EnforcementAction) else None
        topics_joined = " ".join(item.topics)
        self.conn.execute(
            "INSERT OR REPLACE INTO items"
            " (id, type, jurisdiction, title, status, bill_number, agency, docket,"
            "  enacted, public_law, tracking, change_hash, update_date, topics, path)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                "bill" if is_bill else "enforcement",
                item.jurisdiction,
                item.title,
                item.status,
                bill_number,
                agency,
                docket,
                enacted,
                public_law,
                int(item.tracking),
                change_hash,
                update_date,
                json.dumps(item.topics),
                rel_path,
            ),
        )
        self.conn.execute(
            "INSERT INTO items_fts"
            " (id, title, jurisdiction, status, bill_number, topics, agency, docket)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.title,
                item.jurisdiction,
                item.status or "",
                bill_number or "",
                topics_joined,
                agency or "",
                docket or "",
            ),
        )

    # --- queries --------------------------------------------------------

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()
        return int(row[0])

    def get(self, item_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    def tracked(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM items WHERE tracking = 1 ORDER BY id"
        ).fetchall()

    def search(self, query: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT id FROM items_fts WHERE items_fts MATCH ? ORDER BY rank", (query,)
        ).fetchall()
        return [str(row[0]) for row in rows]

    # --- law-brain page cache ------------------------------------------

    def upsert_lawbrain_page(
        self, slug: str, content_hash: str, updated: dt.date | None
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO lawbrain_pages (slug, content_hash, updated, last_seen)"
            " VALUES (?, ?, ?, ?)",
            (
                slug,
                content_hash,
                updated.isoformat() if updated else None,
                dt.datetime.now(dt.UTC).isoformat(),
            ),
        )
        self.conn.commit()

    def lawbrain_hashes(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT slug, content_hash FROM lawbrain_pages").fetchall()
        return {str(row[0]): str(row[1]) for row in rows}
