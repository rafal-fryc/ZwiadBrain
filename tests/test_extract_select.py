"""Operative-document selection for text extraction (PHASE-12).

``select_bill_document`` picks the single most authoritative text version to
extract: the enacted/final text when present, else the latest meaningful
version. Versions without a ``url`` cannot be fetched and are ignored.
"""

import datetime as dt

from zwiadbrain.models import Bill, TextVersion
from zwiadbrain.pipeline.extract import select_bill_document


def _bill(versions: list[TextVersion]) -> Bill:
    return Bill(
        id="119-hr-1",
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        text_versions=versions,
    )


def test_returns_none_when_no_text_versions() -> None:
    assert select_bill_document(_bill([])) is None


def test_returns_none_when_no_version_has_a_url() -> None:
    bill = _bill([TextVersion(code="Introduced", date=dt.date(2025, 1, 1), url=None)])
    assert select_bill_document(bill) is None


def test_prefers_enrolled_over_later_dated_engrossed() -> None:
    bill = _bill(
        [
            TextVersion(code="Introduced in House", date=dt.date(2025, 1, 1), url="https://x/i"),
            TextVersion(code="Enrolled Bill", date=dt.date(2025, 3, 1), url="https://x/enr"),
            TextVersion(code="Engrossed in Senate", date=dt.date(2025, 6, 1), url="https://x/eng"),
        ]
    )
    chosen = select_bill_document(bill)
    assert chosen is not None
    assert chosen.url == "https://x/enr"


def test_prefers_chaptered_state_final_text() -> None:
    bill = _bill(
        [
            TextVersion(code="Introduced", date=dt.date(2025, 1, 1), url="https://x/i"),
            TextVersion(code="Chaptered", date=dt.date(2025, 9, 1), url="https://x/ch"),
        ]
    )
    chosen = select_bill_document(bill)
    assert chosen is not None
    assert chosen.url == "https://x/ch"


def test_falls_back_to_engrossed_when_not_enacted() -> None:
    bill = _bill(
        [
            TextVersion(code="Introduced in House", date=dt.date(2025, 1, 1), url="https://x/i"),
            TextVersion(code="Engrossed in House", date=dt.date(2025, 2, 1), url="https://x/eng"),
        ]
    )
    chosen = select_bill_document(bill)
    assert chosen is not None
    assert chosen.url == "https://x/eng"


def test_falls_back_to_latest_dated_when_only_generic_versions() -> None:
    bill = _bill(
        [
            TextVersion(code="Amended", date=dt.date(2025, 1, 1), url="https://x/a1"),
            TextVersion(code="Amended", date=dt.date(2025, 5, 1), url="https://x/a2"),
        ]
    )
    chosen = select_bill_document(bill)
    assert chosen is not None
    assert chosen.url == "https://x/a2"


def test_ignores_urlless_version_when_choosing_operative() -> None:
    # The enrolled version has no url (can't fetch) -> fall through to a fetchable one.
    bill = _bill(
        [
            TextVersion(code="Introduced", date=dt.date(2025, 1, 1), url="https://x/i"),
            TextVersion(code="Enrolled Bill", date=dt.date(2025, 3, 1), url=None),
        ]
    )
    chosen = select_bill_document(bill)
    assert chosen is not None
    assert chosen.url == "https://x/i"
