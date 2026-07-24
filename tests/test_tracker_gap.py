"""Tests for the external-tracker coverage cross-check and bill-number resolution.

The trackers (Orrick, MultiState) name laws the way lawyers do — ``SB 262``,
``S 1042A``, ``A 10008C`` — while ZwiadBrain ids and LegiScan masterlists use
their own vocabularies (``fl-2023-s-262``, ``SB262``, ``A10008``). Everything here
is about making those three vocabularies meet without HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.tracker_gap import (
    GapEntry,
    SessionBills,
    apply_corrections,
    build_gap,
    entries_from_report,
    entry_payload,
    number_key,
    parse_wiki_id,
    read_snapshot,
    resolve_targets,
    year_hint_from_url,
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


# --- year hints from tracker links ------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://alison.legislature.state.al.us/files/pdf/x/2024RS/HB168-enr.pdf", 2024),
        ("https://leginfo.legislature.ca.gov/faces/bill.xhtml?bill_id=202520260AB325", 2025),
        ("https://www.cga.ct.gov/asp/cgabillstatus.asp?bill_num=SB01103&which_year=2023", 2023),
        ("https://www.legislature.mi.gov/documents/2023-2024/publicact/htm/2023-PA-0263.htm", 2023),
        ("https://le.utah.gov/~2024/bills/static/HB0148.html", 2024),
        ("https://legislature.vermont.gov/bill/status/2022/H.0410", 2022),
        ("https://capitol.texas.gov/tlodocs/89R/billtext/pdf/SB00020F.pdf", 2025),
    ],
)
def test_year_hint_from_url_reads_the_session_year_a_legislature_link_encodes(
    url: str, expected: int
) -> None:
    """should read the session year out of the tracker's own link to the law"""
    assert year_hint_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.legmt.gov/download-ticket?ticketId=a64e8bac-75d1-42b8-a672-82870e842ab0",
        "https://sdlegislature.gov/Session/Bill/24991",
        "https://nebraskalegislature.gov/FloorDocs/109/PDF/Slip/LB383.pdf",
        "",
    ],
)
def test_year_hint_from_url_returns_none_when_the_link_encodes_no_year(url: str) -> None:
    """should return None rather than key on a digit run that is not a session year"""
    assert year_hint_from_url(url) is None


def test_year_hint_from_url_ignores_an_orrick_cdn_publication_date() -> None:
    """should not read Orrick's own media-library path year as a session year"""
    url = "https://media.orrick.com/Media%20Library/public/files/ailawcenter/2026/04/lb525.pdf"
    assert year_hint_from_url(url) is None


def test_year_hint_from_url_still_reads_a_year_in_an_orrick_filename() -> None:
    """should keep the session year when Orrick's re-hosted filename carries it"""
    url = "https://infobytes.orrick.com/wp-content/uploads/Arizona-2025-SB1462-Engrossed.pdf"
    assert year_hint_from_url(url) == 2025


def test_year_hint_from_url_ignores_a_year_outside_the_plausible_range() -> None:
    """should reject an out-of-range year so a stray digit run cannot become a hint"""
    assert year_hint_from_url("https://example.test/docs/2099/HB1.pdf") is None


def test_read_snapshot_falls_back_to_the_link_year_for_an_orrick_row() -> None:
    """should hint an Orrick row from its law_link, since its bill_key has no year"""
    snap = {
        "laws": [
            {"jurisdiction": "US-AL", "state": "Alabama", "orrick_topic": "AI CSAM",
             "name": "Alabama Child Protection Act of 2024", "bill_number": "HB 168",
             "bill_key": "al-hb-168",
             "law_link": "https://alison.legislature.state.al.us/x/2024RS/HB168-enr.pdf"},
        ]
    }
    laws, _ = read_snapshot(snap)
    assert laws[0].year_hint == 2024


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


# --- corrections ------------------------------------------------------------


def _correctable() -> list[Any]:
    snap = {
        "laws": [
            {"jurisdiction": "US-VA", "state": "Virginia", "orrick_topic": "AI Intimate Images",
             "name": "Amendment to the Unlawful Dissemination of Images statute",
             "bill_number": "B 2678", "bill_key": "va-b-2678", "law_link": None},
            {"jurisdiction": "US-MT", "state": "Montana", "orrick_topic": "AI in Government",
             "name": "Montana Government AI Use Law", "bill_number": "HB 178",
             "bill_key": "mt-hb-178", "law_link": "https://docs.legmt.gov/x?ticketId=abc"},
        ]
    }
    laws, _ = read_snapshot(snap)
    return laws


def test_apply_corrections_fixes_a_tracker_bill_number() -> None:
    """should replace a bill number the tracker recorded wrong"""
    corrections = {
        "corrections": [
            {"state": "va", "bill_number": "B 2678", "correct_number": "HB 2678",
             "why": "anchor text lost the chamber prefix"}
        ]
    }
    fixed = apply_corrections(_correctable(), corrections)
    assert fixed[0].bill_number == "HB 2678"


def test_apply_corrections_pins_a_session_year_the_link_does_not_encode() -> None:
    """should set a year hint for a law whose tracker link is an opaque document id"""
    corrections = {
        "corrections": [
            {"state": "mt", "bill_number": "HB 178", "year": 2025, "why": "opaque link"}
        ]
    }
    fixed = apply_corrections(_correctable(), corrections)
    assert fixed[1].year_hint == 2025


def test_apply_corrections_refiles_a_law_the_tracker_put_under_the_wrong_state() -> None:
    """should move a mis-filed law to its real jurisdiction, key and all"""
    corrections = {
        "corrections": [
            {"state": "va", "bill_number": "B 2678", "correct_state": "tn",
             "correct_number": "SB 837", "why": "tracker filed a TN law under VA"}
        ]
    }
    fixed = apply_corrections(_correctable(), corrections)
    assert fixed[0].state == "tn"
    assert fixed[0].jurisdiction == "US-TN"
    assert fixed[0].bill_number == "SB 837"


def test_apply_corrections_leaves_uncorrected_laws_untouched() -> None:
    """should pass through every law no correction names"""
    assert apply_corrections(_correctable(), {"corrections": []}) == _correctable()


def test_apply_corrections_drops_an_explicitly_excluded_row() -> None:
    """should drop a tracker row we have decided the pipeline cannot or should not track"""
    corrections = {
        "exclusions": [{"state": "mt", "bill_number": "HB 178", "why": "not in LegiScan"}]
    }
    fixed = apply_corrections(_correctable(), corrections)
    assert [law.bill_number for law in fixed] == ["B 2678"]


def test_apply_corrections_rejects_an_exclusion_that_matches_nothing() -> None:
    """should fail loudly on a stale exclusion, same as a stale correction"""
    corrections = {"exclusions": [{"state": "mt", "bill_number": "HB 1", "why": "stale"}]}
    with pytest.raises(ConfigError, match="matches no tracker law"):
        apply_corrections(_correctable(), corrections)


def test_apply_corrections_rejects_a_correction_that_matches_nothing() -> None:
    """should fail loudly on a stale correction rather than silently doing nothing"""
    corrections = {
        "corrections": [{"state": "va", "bill_number": "HB 9999", "year": 2019, "why": "typo"}]
    }
    with pytest.raises(ConfigError, match="matches no tracker law"):
        apply_corrections(_correctable(), corrections)


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
