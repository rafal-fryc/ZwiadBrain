"""Tests for the external-tracker coverage cross-check and bill-number resolution.

The trackers (Orrick, MultiState) name laws the way lawyers do — ``SB 262``,
``S 1042A``, ``A 10008C`` — while ZwiadBrain ids and LegiScan masterlists use
their own vocabularies (``fl-2023-s-262``, ``SB262``, ``A10008``). Everything here
is about making those three vocabularies meet without HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest

from zwiadbrain.pipeline.tracker_gap import (
    GapEntry,
    SessionBills,
    build_gap,
    entries_from_report,
    entry_payload,
    number_key,
    parse_wiki_id,
    read_snapshot,
    resolve_targets,
)
from zwiadbrain.sources.base import Candidate
from zwiadbrain.sources.legiscan import Session

# --- number normalization ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SB 262", ("S", "262")),
        ("sb262", ("S", "262")),
        ("S 262", ("S", "262")),
        ("HB 168", ("H", "168")),
        ("H 7281", ("H", "7281")),
        ("AB 2905", ("H", "2905")),      # CA Assembly -> lower chamber
        ("A 10008C", ("H", "10008")),    # NY print letter dropped
        ("S 1042A", ("S", "1042")),
        ("HF 2635", ("H", "2635")),      # IA House File
        ("SF 4097", ("S", "4097")),
        ("HP 1397", ("H", "1397")),      # ME House Paper
        ("LD 1727", ("LD", "1727")),     # ME legislative document — own vocabulary
        ("LB 383", ("LB", "383")),       # NE unicameral
        ("SB 0063", ("S", "63")),        # leading zeros stripped
    ],
)
def test_number_key_normalizes_tracker_and_legiscan_vocabularies(
    raw: str, expected: tuple[str, str]
) -> None:
    """should reduce a bill number to (chamber class, digits) across both vocabularies"""
    assert number_key(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "Chapter 7.5", "HB"])
def test_number_key_returns_none_for_a_non_bill_number(raw: str) -> None:
    """should return None when there is no trailing digit run to key on"""
    assert number_key(raw) is None


def test_number_key_matches_a_tracker_number_to_its_legiscan_form() -> None:
    """should give the tracker's 'SB 262' and LegiScan's 'S262' the same key"""
    assert number_key("SB 262") == number_key("S262")


# --- wiki id parsing --------------------------------------------------------


def test_parse_wiki_id_splits_key_and_session_year() -> None:
    """should split a wiki bill id into its join key and its session year"""
    assert parse_wiki_id("fl-2023-s-262") == (("fl", "S", "262"), 2023)
    assert parse_wiki_id("ca-2023-ab-1836") == (("ca", "H", "1836"), 2023)
    assert parse_wiki_id("me-2025-ld-1727") == (("me", "LD", "1727"), 2025)


def test_parse_wiki_id_returns_none_for_a_federal_id() -> None:
    """should return None for a federal id, which has no state segment"""
    assert parse_wiki_id("118-hr-2670") is None


# --- snapshot reading -------------------------------------------------------


def _snapshot() -> dict[str, Any]:
    return {
        "laws": [
            {
                "jurisdiction": "US-FL",
                "state": "Florida",
                "orrick_topic": "Automated Decision-Making",
                "name": "Florida Digital Bill of Rights",
                "bill_number": "SB 262",
                "citation": None,
                "bill_key": "fl-sb-262",
                "law_link": "https://example.test/fl262",
            },
            {
                "jurisdiction": "US-CA",
                "state": "California",
                "orrick_topic": "AI Transparency",
                "name": "California AI Transparency Act",
                "bill_number": None,
                "citation": "Cal. Bus. & Prof. Code 22757 et seq.",
                "bill_key": None,
                "law_link": "https://example.test/ca22757",
            },
        ],
        "multistate_enacted_laws": [
            {
                "jurisdiction": "US-CT",
                "state": "Connecticut",
                "bill_number": "HB 5222",
                "title": "An Act Concerning Consumer Protection",
                "bill_key": "ct-2026-hb-5222",
                "multistate_tag": "Artificial Intelligence",
                "source_url": "https://example.test/ct5222",
            },
        ],
    }


def test_read_snapshot_reads_both_source_lists_and_separates_citation_rows() -> None:
    """should yield bill-numbered laws from both lists and citation-only rows apart"""
    laws, citations = read_snapshot(_snapshot())
    assert [(law.source, law.state, law.bill_number) for law in laws] == [
        ("orrick", "fl", "SB 262"),
        ("multistate", "ct", "HB 5222"),
    ]
    assert [(c.source, c.state, c.citation) for c in citations] == [
        ("orrick", "ca", "Cal. Bus. & Prof. Code 22757 et seq.")
    ]


def test_read_snapshot_takes_the_year_hint_only_from_the_multistate_key() -> None:
    """should carry MultiState's session year as a hint; Orrick keys have none"""
    laws, _ = read_snapshot(_snapshot())
    assert laws[0].year_hint is None
    assert laws[1].year_hint == 2026


# --- gap bucketing ----------------------------------------------------------


def test_build_gap_buckets_by_tracked_then_rejected_then_gap() -> None:
    """should bucket each law as tracked, already-rejected, or a true gap"""
    laws, _ = read_snapshot(_snapshot())
    report = build_gap(laws, tracked_ids=["fl-2023-s-262"], rejected_ids=["ct-2026-hb-5222"])
    assert [e.bill_number for e in report.tracked] == ["SB 262"]
    assert [e.bill_number for e in report.rejected] == ["HB 5222"]
    assert report.gap == []


def test_build_gap_ignores_the_session_year_when_matching() -> None:
    """should treat a tracked page from another session as covering the same law"""
    laws, _ = read_snapshot(_snapshot())
    report = build_gap(laws, tracked_ids=["ct-2025-hb-5222"], rejected_ids=[])
    assert [e.bill_number for e in report.tracked] == ["HB 5222"]


def test_build_gap_flags_a_tracked_match_whose_session_year_differs() -> None:
    """should report a year-agnostic match so a reused bill number can be eyeballed"""
    laws, _ = read_snapshot(_snapshot())
    report = build_gap(laws, tracked_ids=["ct-2025-hb-5222"], rejected_ids=[])
    assert [(m.bill_number, m.year_hint, m.wiki_ids) for m in report.year_mismatch] == [
        ("HB 5222", 2026, ["ct-2025-hb-5222"])
    ]


def test_build_gap_merges_a_law_listed_once_per_topic_into_one_entry() -> None:
    """should collapse a tracker's per-topic duplicate rows into a single gap entry"""
    snap = {
        "laws": [
            {"jurisdiction": "US-UT", "state": "Utah", "orrick_topic": "AI CSAM",
             "name": "Digital Voyeurism Prevention Act", "bill_number": "HB 276",
             "bill_key": "ut-hb-276", "law_link": "https://example.test/a"},
            {"jurisdiction": "US-UT", "state": "Utah", "orrick_topic": "AI in Government",
             "name": "Government Website Provenance Records", "bill_number": "HB 276",
             "bill_key": "ut-hb-276", "law_link": "https://example.test/b"},
        ]
    }
    laws, _ = read_snapshot(snap)
    report = build_gap(laws, tracked_ids=[], rejected_ids=[])
    assert len(report.gap) == 1
    entry = report.gap[0]
    assert entry.topics == ["AI CSAM", "AI in Government"]
    assert len(entry.names) == 2


def test_build_gap_records_both_sources_when_the_trackers_overlap() -> None:
    """should mark a law that both trackers list as coming from both"""
    snap = {
        "laws": [
            {"jurisdiction": "US-CT", "state": "Connecticut", "orrick_topic": "AI Transparency",
             "name": "Connecticut Data Privacy Act", "bill_number": "HB 5222",
             "bill_key": "ct-hb-5222", "law_link": None},
        ],
        "multistate_enacted_laws": [
            {"jurisdiction": "US-CT", "state": "Connecticut", "bill_number": "HB 5222",
             "title": "An Act Concerning Consumer Protection", "bill_key": "ct-2026-hb-5222",
             "multistate_tag": "Artificial Intelligence", "source_url": None},
        ],
    }
    laws, _ = read_snapshot(snap)
    report = build_gap(laws, tracked_ids=[], rejected_ids=[])
    assert report.gap[0].sources == ["orrick", "multistate"]


def test_build_gap_skips_a_law_whose_number_cannot_be_keyed() -> None:
    """should drop an unkeyable row rather than emit a bogus target"""
    snap = {"laws": [
        {"jurisdiction": "US-CA", "state": "California", "orrick_topic": "AI CSAM",
         "name": "Amendment of CSAM Laws", "bill_number": "Chapter 7.5",
         "bill_key": "ca-chapter-75", "law_link": None},
    ]}
    laws, _ = read_snapshot(snap)
    report = build_gap(laws, tracked_ids=[], rejected_ids=[])
    assert report.gap == []
    assert [law.bill_number for law in report.unkeyable] == ["Chapter 7.5"]


# --- report round-trip ------------------------------------------------------


def test_entries_from_report_round_trips_a_serialized_gap_entry() -> None:
    """should read back exactly what entry_payload wrote"""
    laws, _ = read_snapshot(_snapshot())
    report = build_gap(laws, tracked_ids=[], rejected_ids=[])
    payload = {"gap": [entry_payload(e) for e in report.gap]}
    assert entries_from_report(payload) == report.gap


def test_entries_from_report_filters_to_one_state() -> None:
    """should return only the requested state's targets"""
    laws, _ = read_snapshot(_snapshot())
    report = build_gap(laws, tracked_ids=[], rejected_ids=[])
    payload = {"gap": [entry_payload(e) for e in report.gap]}
    assert [e.state for e in entries_from_report(payload, state="ct")] == ["ct"]


def test_entries_from_report_skips_a_row_whose_number_no_longer_keys() -> None:
    """should drop a hand-edited row the matcher could never resolve"""
    payload = {"gap": [{"state": "ca", "bill_number": "Chapter 7.5", "key": ["ca", "H", "1"]}]}
    assert entries_from_report(payload) == []


# --- target resolution against LegiScan sessions ----------------------------


def _entry(state: str, number: str, *, year_hint: int | None = None) -> GapEntry:
    return GapEntry(
        key=(state, *number_key(number)),  # type: ignore[misc]
        state=state,
        jurisdiction=f"US-{state.upper()}",
        bill_number=number,
        names=["A law"],
        topics=["AI"],
        sources=["orrick"],
        year_hint=year_hint,
        urls=[],
    )


def _cand(native_id: str, number: str, state: str = "ut") -> Candidate:
    return Candidate(
        source="legiscan",
        native_id=native_id,
        jurisdiction=f"US-{state.upper()}",
        title=f"{number} title",
        summary=None,
        raw={"number": number, "status": 4},
    )


def _session(session_id: int, year_start: int, year_end: int) -> Session:
    return Session(
        session_id=session_id,
        year_start=year_start,
        year_end=year_end,
        special=False,
        session_name=f"{year_start} Session",
    )


def test_resolve_targets_matches_a_tracker_number_to_its_legiscan_bill() -> None:
    """should resolve 'HB 276' to the masterlist row numbered HB276"""
    entries = [_entry("ut", "HB 276")]
    sessions = [SessionBills(_session(2020, 2026, 2026), [_cand("991", "HB276")])]
    [res] = resolve_targets(entries, sessions)
    assert res.status == "resolved"
    assert res.candidate is not None
    assert res.candidate.native_id == "991"
    assert res.session_id == 2020


def test_resolve_targets_reports_a_target_absent_from_every_session() -> None:
    """should report not-found rather than silently dropping an unmatched target"""
    entries = [_entry("ut", "HB 999")]
    sessions = [SessionBills(_session(2020, 2026, 2026), [_cand("991", "HB276")])]
    [res] = resolve_targets(entries, sessions)
    assert res.status == "not-found"
    assert res.candidate is None


def test_resolve_targets_prefers_the_session_covering_the_year_hint() -> None:
    """should pick the hinted session when the same number is enacted in two sessions"""
    entries = [_entry("ut", "HB 276", year_hint=2024)]
    sessions = [
        SessionBills(_session(2020, 2026, 2026), [_cand("991", "HB276")]),
        SessionBills(_session(1900, 2024, 2024), [_cand("550", "HB276")]),
    ]
    [res] = resolve_targets(entries, sessions)
    assert res.status == "resolved"
    assert res.candidate is not None
    assert res.candidate.native_id == "550"


def test_resolve_targets_reports_ambiguity_when_no_hint_disambiguates() -> None:
    """should refuse to guess between sessions and report the candidates instead"""
    entries = [_entry("ut", "HB 276")]
    sessions = [
        SessionBills(_session(2020, 2026, 2026), [_cand("991", "HB276")]),
        SessionBills(_session(1900, 2024, 2024), [_cand("550", "HB276")]),
    ]
    [res] = resolve_targets(entries, sessions)
    assert res.status == "ambiguous"
    assert res.candidate is None
    assert "991" in res.detail and "550" in res.detail


def test_resolve_targets_scans_the_newest_session_first() -> None:
    """should prefer the newest session when an unhinted number appears only once"""
    entries = [_entry("ut", "HB 276")]
    sessions = [
        SessionBills(_session(1900, 2024, 2024), [_cand("550", "SB276")]),
        SessionBills(_session(2020, 2026, 2026), [_cand("991", "HB276")]),
    ]
    [res] = resolve_targets(entries, sessions)
    assert res.candidate is not None
    assert res.candidate.native_id == "991"
