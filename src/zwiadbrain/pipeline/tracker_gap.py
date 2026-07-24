"""External AI-law-tracker coverage cross-check and bill-number resolution (PHASE-29).

Two external trackers are snapshotted in ``reference/orrick-ai-tracker-2026-07.yaml``
— Orrick's US AI Law Tracker (``laws``) and MultiState's AI Legislation Tracker
(``multistate_enacted_laws``). Each names a law the way a lawyer cites it (``SB 262``,
``S 1042A``); ZwiadBrain names it ``fl-2023-s-262``; LegiScan's masterlist names it
``S262``. This module is where the three vocabularies meet.

Everything here is pure — the caller does the HTTP and the file IO — so the join and
the session-scan can be tested without touching LegiScan.

Two stages:

**Cross-check** (:func:`read_snapshot` + :func:`build_gap`) buckets every tracked law
into *tracked* (a wiki page exists), *rejected* (decided out-of-scope in the reject
ledger), or *gap* (never seen by the pipeline). The join deliberately ignores the
session year, because Orrick's rows carry only an effective date; a match whose year
disagrees is reported in ``year_mismatch`` so a reused bill number can be eyeballed
rather than silently trusted.

**Resolution** (:func:`resolve_targets`) turns a gap entry into a LegiScan ``bill_id``
by scanning the state's sessions' enacted masterlists. It never guesses: a number
enacted in two sessions with no year hint to separate them is reported ``ambiguous``,
not resolved to the newest.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, cast

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.sources.base import Candidate
from zwiadbrain.sources.legiscan import Session

# A bill number is a leading non-digit prefix and a trailing digit run, optionally
# followed by a print letter (NY's ``S 1042A`` is the third print of ``S 1042``, not
# a different bill). Whitespace and punctuation between the two are noise.
_NUMBER_RE = re.compile(r"^\s*([A-Za-z]+)[\s.\-]*(\d+)\s*([A-Za-z]?)\s*$")

# Chamber prefixes collapse to a chamber CLASS so that a tracker's ``SB``/``S`` and a
# state's own ``AB``/``A``/``HF``/``HP`` all meet. An EXCLUDE-by-omission design: a
# prefix in neither set (ME ``LD``, NE ``LB``) keeps its own uppercased vocabulary,
# which is still stable across the three naming systems for those states.
_LOWER_CHAMBER = frozenset({"h", "hb", "a", "ab", "hf", "hp", "ahb"})
_UPPER_CHAMBER = frozenset({"s", "sb", "sf", "sp", "asb"})

Key = tuple[str, str, str]
"""A law's join identity: ``(state, chamber class, digits)`` — no session year."""

# --- wiki id: <st>-<year>-<chamber>-<number> ---------------------------------
_WIKI_ID_RE = re.compile(r"^([a-z]{2})-(\d{4})-([a-z]+)-(\d+[a-z]?)$")
# --- multistate bill_key: <st>-<year>-<chamber>-<number> ---------------------
_MULTISTATE_KEY_RE = _WIKI_ID_RE


def number_key(bill_number: str) -> tuple[str, str] | None:
    """Reduce a bill number to ``(chamber class, digits)``, or None if it is not one.

    ``"SB 262"``, ``"sb262"`` and LegiScan's ``"S262"`` all key to ``("S", "262")``;
    ``"A 10008C"`` keys to ``("H", "10008")``. Leading zeros are stripped so a
    tracker's ``SB 0063`` meets LegiScan's ``SB63``.
    """
    match = _NUMBER_RE.match(bill_number)
    if match is None:
        return None
    prefix = match.group(1).lower()
    digits = match.group(2).lstrip("0") or "0"
    if prefix in _LOWER_CHAMBER:
        return "H", digits
    if prefix in _UPPER_CHAMBER:
        return "S", digits
    return prefix.upper(), digits


def parse_wiki_id(bill_id: str) -> tuple[Key, int] | None:
    """Split a state wiki id into its join key and session year, or None if not one.

    ``"fl-2023-s-262"`` -> ``(("fl", "S", "262"), 2023)``. A federal id
    (``"118-hr-2670"``) has no two-letter state segment and returns None.
    """
    match = _WIKI_ID_RE.match(bill_id)
    if match is None:
        return None
    state, year, chamber, digits = match.groups()
    keyed = number_key(f"{chamber}{digits}")
    if keyed is None:
        return None
    return (state, *keyed), int(year)


@dataclass(frozen=True)
class TrackerLaw:
    """One tracker row that names a bill by number."""

    source: str  # "orrick" | "multistate"
    state: str  # two-letter, lowercase
    jurisdiction: str
    bill_number: str  # verbatim from the tracker
    name: str
    topic: str | None
    year_hint: int | None  # MultiState keys carry the session year; Orrick's do not
    url: str | None


@dataclass(frozen=True)
class CitationRow:
    """One tracker row that cites a statute instead of naming a bill.

    These cannot be resolved through LegiScan by construction — some are laws we
    already track under their bill number, some are administrative regulations that
    never had a bill at all.
    """

    source: str
    state: str
    jurisdiction: str
    citation: str
    name: str
    topic: str | None
    url: str | None


# A session year in a legislature URL — '/2024RS/', 'bill_id=202520260AB325',
# 'which_year=2023', '/~2024/bills/'. Digit-boundary anchored so a UUID or an opaque
# document id cannot masquerade as a year.
_URL_YEAR_RE = re.compile(r"(?<!\d)(20[0-2]\d)(?!\d)")
_URL_YEAR_RANGE = range(2015, 2028)
# Texas encodes the legislature, not the year: '/tlodocs/89R/billtext/...'.
_TX_LEG_RE = re.compile(r"/tlodocs/(\d\d)[RSrs]\d?/")
_TX_LEG_YEAR = {"86": 2019, "87": 2021, "88": 2023, "89": 2025, "90": 2027}
# California packs both session years into one unbroken run: 'bill_id=202520260AB325'.
_CA_BILL_ID_RE = re.compile(r"bill_id=(20[0-2]\d)\d{5}", re.IGNORECASE)
_ORRICK_HOST_RE = re.compile(r"https?://[^/]*\borrick\.com/", re.IGNORECASE)


def year_hint_from_url(url: str) -> int | None:
    """Read the session year a tracker's link to the law encodes, or None.

    Orrick's ``bill_key`` carries no session year, but its ``law_link`` almost always
    points at a legislature URL that does. The hint is only ever used to *narrow* an
    otherwise-ambiguous number match, and a hint matching no session leaves the entry
    ambiguous — so a wrong hint cannot silently resolve to the wrong bill.
    """
    if not url:
        return None
    tx = _TX_LEG_RE.search(url)
    if tx is not None:
        return _TX_LEG_YEAR.get(tx.group(1))
    ca = _CA_BILL_ID_RE.search(url)
    if ca is not None:
        year = int(ca.group(1))
        return year if year in _URL_YEAR_RANGE else None
    # Orrick re-hosts some laws on its own CDN, whose directory path is a PUBLICATION
    # date, not a session year ('.../ailawcenter/2026/04/lb525.pdf' is a 2025 law). Only
    # the filename is trusted there — its re-host names do carry the session year
    # ('Arizona-2025-SB1462-Engrossed.pdf').
    haystack = url.rsplit("/", 1)[-1] if _ORRICK_HOST_RE.search(url) else url
    for match in _URL_YEAR_RE.finditer(haystack):
        year = int(match.group(1))
        if year in _URL_YEAR_RANGE:
            return year
    return None


def _opt(value: object) -> str | None:
    """Coerce a snapshot field to ``str | None`` (YAML nulls arrive as ``None``)."""
    return None if value is None else str(value)


def read_snapshot(data: dict[str, Any]) -> tuple[list[TrackerLaw], list[CitationRow]]:
    """Read both tracker lists out of the snapshot, separating citation-only rows."""
    laws: list[TrackerLaw] = []
    citations: list[CitationRow] = []
    orrick_rows = cast(list[dict[str, Any]], data.get("laws") or [])
    multistate_rows = cast(list[dict[str, Any]], data.get("multistate_enacted_laws") or [])
    for row in orrick_rows:
        state = str(row["jurisdiction"]).removeprefix("US-").lower()
        number = row.get("bill_number")
        if not number:
            citations.append(
                CitationRow(
                    source="orrick",
                    state=state,
                    jurisdiction=str(row["jurisdiction"]),
                    citation=str(row.get("citation") or ""),
                    name=str(row.get("name") or ""),
                    topic=_opt(row.get("orrick_topic")),
                    url=_opt(row.get("law_link")),
                )
            )
            continue
        law_link = _opt(row.get("law_link"))
        laws.append(
            TrackerLaw(
                source="orrick",
                state=state,
                jurisdiction=str(row["jurisdiction"]),
                bill_number=str(number),
                name=str(row.get("name") or ""),
                topic=_opt(row.get("orrick_topic")),
                # Orrick's bill_key has no session year and its effective date can lag
                # enactment by years, so the hint comes from its link to the law instead.
                year_hint=year_hint_from_url(law_link or ""),
                url=law_link,
            )
        )
    for row in multistate_rows:
        state = str(row["jurisdiction"]).removeprefix("US-").lower()
        key_match = _MULTISTATE_KEY_RE.match(str(row.get("bill_key") or ""))
        laws.append(
            TrackerLaw(
                source="multistate",
                state=state,
                jurisdiction=str(row["jurisdiction"]),
                bill_number=str(row.get("bill_number") or ""),
                name=str(row.get("title") or ""),
                topic=_opt(row.get("multistate_tag")),
                year_hint=int(key_match.group(2)) if key_match else None,
                url=_opt(row.get("source_url")),
            )
        )
    return laws, citations


def apply_corrections(
    laws: list[TrackerLaw], data: dict[str, Any]
) -> list[TrackerLaw]:
    """Apply hand-verified corrections to the tracker rows before the cross-check.

    Three kinds, all keyed by ``(state, the tracker's verbatim bill_number)``:
    ``correct_number`` fixes a tracker-side data error (Orrick's Law Link anchor text
    occasionally drops a chamber prefix), ``correct_state`` re-files a law the tracker
    put under the wrong jurisdiction, and ``year`` pins a session year the tracker's
    own link does not encode (an opaque document-id URL). Each correction carries a
    ``why``.

    A correction that matches no tracker law raises :class:`ConfigError` — a stale
    correction means the snapshot moved under it, and silently ignoring it would hide
    the drift.
    """
    entries = cast(list[dict[str, Any]], data.get("corrections") or [])
    dropped = cast(list[dict[str, Any]], data.get("exclusions") or [])
    index: dict[tuple[str, str], dict[str, Any]] = {
        (str(e["state"]).lower(), str(e["bill_number"])): e for e in entries
    }
    excluded: dict[tuple[str, str], dict[str, Any]] = {
        (str(e["state"]).lower(), str(e["bill_number"])): e for e in dropped
    }
    used: set[tuple[str, str]] = set()
    out: list[TrackerLaw] = []
    for law in laws:
        key = (law.state, law.bill_number)
        if key in excluded:
            used.add(key)
            continue
        fix = index.get(key)
        if fix is None:
            out.append(law)
            continue
        used.add(key)
        year = fix.get("year")
        state = str(fix.get("correct_state") or law.state).lower()
        out.append(
            replace(
                law,
                state=state,
                jurisdiction=f"US-{state.upper()}",
                bill_number=str(fix.get("correct_number") or law.bill_number),
                year_hint=int(year) if year is not None else law.year_hint,
            )
        )
    unused = sorted((set(index) | set(excluded)) - used)
    if unused:
        listed = ", ".join(f"{s} {n}" for s, n in unused)
        raise ConfigError(f"tracker correction matches no tracker law: {listed}")
    return out


@dataclass
class GapEntry:
    """One law, merged across every tracker row that names it.

    A tracker lists a law once per topic tag, and both trackers can list the same
    law, so ``names``/``topics``/``sources`` accumulate.
    """

    key: Key
    state: str
    jurisdiction: str
    bill_number: str
    names: list[str] = field(default_factory=list[str])
    topics: list[str] = field(default_factory=list[str])
    sources: list[str] = field(default_factory=list[str])
    year_hint: int | None = None
    urls: list[str] = field(default_factory=list[str])
    wiki_ids: list[str] = field(default_factory=list[str])
    reject_ids: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class GapReport:
    tracked: list[GapEntry]
    rejected: list[GapEntry]
    gap: list[GapEntry]
    # Tracked matches whose wiki session year disagrees with the tracker's — a state
    # can reuse a bill number across sessions, so these want a human glance.
    year_mismatch: list[GapEntry]
    # Rows whose bill_number could not be keyed (a statute cite in the number field).
    unkeyable: list[TrackerLaw]


def _index(bill_ids: Iterable[str]) -> dict[Key, list[str]]:
    index: dict[Key, list[str]] = {}
    for bill_id in bill_ids:
        parsed = parse_wiki_id(str(bill_id))
        if parsed is None:
            continue
        index.setdefault(parsed[0], []).append(str(bill_id))
    return index


def _years(bill_ids: list[str]) -> set[int]:
    return {parsed[1] for bid in bill_ids if (parsed := parse_wiki_id(bid)) is not None}


def build_gap(
    laws: list[TrackerLaw], *, tracked_ids: Iterable[str], rejected_ids: Iterable[str]
) -> GapReport:
    """Bucket every tracker law as tracked, already-rejected, or a true gap.

    ``tracked_ids`` are wiki page ids (``fl-2023-s-262``); ``rejected_ids`` are the
    ``id`` values in the state reject ledger. Both are matched year-agnostically.
    """
    have, rejected = _index(tracked_ids), _index(rejected_ids)
    buckets: dict[str, dict[Key, GapEntry]] = {"tracked": {}, "rejected": {}, "gap": {}}
    unkeyable: list[TrackerLaw] = []
    mismatch_keys: set[Key] = set()

    for law in laws:
        keyed = number_key(law.bill_number)
        if keyed is None:
            unkeyable.append(law)
            continue
        key: Key = (law.state, *keyed)
        bucket = "tracked" if key in have else "rejected" if key in rejected else "gap"
        entry = buckets[bucket].setdefault(
            key,
            GapEntry(
                key=key,
                state=law.state,
                jurisdiction=law.jurisdiction,
                bill_number=law.bill_number,
                wiki_ids=have.get(key, []),
                reject_ids=rejected.get(key, []),
            ),
        )
        for values, value in (
            (entry.names, law.name),
            (entry.topics, law.topic),
            (entry.sources, law.source),
            (entry.urls, law.url),
        ):
            if value and value not in values:
                values.append(value)
        if law.year_hint is not None:
            entry.year_hint = law.year_hint
            if bucket == "tracked" and law.year_hint not in _years(have[key]):
                mismatch_keys.add(key)

    def ordered(bucket: str) -> list[GapEntry]:
        return sorted(buckets[bucket].values(), key=lambda e: (e.state, e.key[1], int(e.key[2])))

    return GapReport(
        tracked=ordered("tracked"),
        rejected=ordered("rejected"),
        gap=ordered("gap"),
        year_mismatch=[e for e in ordered("tracked") if e.key in mismatch_keys],
        unkeyable=unkeyable,
    )


def entry_payload(entry: GapEntry) -> dict[str, Any]:
    """Serialize a gap entry for the ``tracker-gap`` report."""
    return {
        "key": list(entry.key),
        "state": entry.state,
        "jurisdiction": entry.jurisdiction,
        "bill_number": entry.bill_number,
        "names": entry.names,
        "topics": entry.topics,
        "sources": entry.sources,
        "year_hint": entry.year_hint,
        "urls": entry.urls,
        "wiki_ids": entry.wiki_ids,
        "reject_ids": entry.reject_ids,
    }


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def entries_from_report(data: dict[str, Any], *, state: str | None = None) -> list[GapEntry]:
    """Read the ``gap`` list back out of a ``tracker-gap`` report, optionally per state.

    The inverse of :func:`entry_payload`. Rows whose bill number no longer keys are
    skipped rather than trusted from the persisted key, so a hand-edited report cannot
    smuggle in a target the matcher could never resolve.
    """
    rows = cast(list[dict[str, Any]], data.get("gap") or [])
    entries: list[GapEntry] = []
    for row in rows:
        row_state = str(row.get("state") or "")
        if state is not None and row_state != state.lower():
            continue
        bill_number = str(row.get("bill_number") or "")
        keyed = number_key(bill_number)
        if keyed is None:
            continue
        year_hint = row.get("year_hint")
        entries.append(
            GapEntry(
                key=(row_state, *keyed),
                state=row_state,
                jurisdiction=str(row.get("jurisdiction") or ""),
                bill_number=bill_number,
                names=_str_list(row.get("names")),
                topics=_str_list(row.get("topics")),
                sources=_str_list(row.get("sources")),
                year_hint=int(year_hint) if year_hint is not None else None,
                urls=_str_list(row.get("urls")),
                wiki_ids=_str_list(row.get("wiki_ids")),
                reject_ids=_str_list(row.get("reject_ids")),
            )
        )
    return entries


# --- resolution against LegiScan sessions -----------------------------------


@dataclass(frozen=True)
class SessionBills:
    """One session's enacted masterlist, as fetched by the caller."""

    session: Session
    candidates: list[Candidate]


@dataclass(frozen=True)
class Resolution:
    """The outcome of matching one gap entry against a state's sessions."""

    entry: GapEntry
    candidate: Candidate | None
    session_id: int | None
    status: str  # "resolved" | "not-found" | "ambiguous"
    detail: str


def _covers(session: Session, year: int) -> bool:
    return session.year_start <= year <= session.year_end


def resolve_targets(
    entries: list[GapEntry], sessions: list[SessionBills]
) -> list[Resolution]:
    """Match each gap entry to its LegiScan bill via the sessions' enacted masterlists.

    Sessions are scanned newest-first. A number found in exactly one session resolves.
    A number found in several resolves only when a ``year_hint`` picks one out —
    otherwise it is reported ``ambiguous`` rather than guessed, because picking the
    newest would silently mistrack a state that reuses bill numbers each biennium.
    """
    ordered = sorted(
        sessions,
        key=lambda s: (s.session.year_start, s.session.session_id),
        reverse=True,
    )
    index: list[tuple[SessionBills, dict[tuple[str, str], list[Candidate]]]] = []
    for bills in ordered:
        by_number: dict[tuple[str, str], list[Candidate]] = {}
        for candidate in bills.candidates:
            keyed = number_key(str(candidate.raw.get("number") or ""))
            if keyed is not None:
                by_number.setdefault(keyed, []).append(candidate)
        index.append((bills, by_number))

    resolutions: list[Resolution] = []
    for entry in entries:
        keyed = (entry.key[1], entry.key[2])
        hits = [
            (bills, candidate)
            for bills, by_number in index
            for candidate in by_number.get(keyed, [])
        ]
        if not hits:
            scanned = ", ".join(str(b.session.session_id) for b, _ in index) or "none"
            resolutions.append(
                Resolution(
                    entry=entry,
                    candidate=None,
                    session_id=None,
                    status="not-found",
                    detail=f"{entry.bill_number} absent from enacted masterlists: {scanned}",
                )
            )
            continue
        if len(hits) > 1 and entry.year_hint is not None:
            hinted = [h for h in hits if _covers(h[0].session, entry.year_hint)]
            if len(hinted) == 1:
                hits = hinted
        if len(hits) > 1:
            listed = ", ".join(
                f"{c.native_id}@session {b.session.session_id}" for b, c in hits
            )
            resolutions.append(
                Resolution(
                    entry=entry,
                    candidate=None,
                    session_id=None,
                    status="ambiguous",
                    detail=f"{entry.bill_number} enacted in >1 session: {listed}",
                )
            )
            continue
        bills, candidate = hits[0]
        resolutions.append(
            Resolution(
                entry=entry,
                candidate=candidate,
                session_id=bills.session.session_id,
                status="resolved",
                detail=f"{entry.bill_number} -> bill_id {candidate.native_id}"
                f" (session {bills.session.session_id})",
            )
        )
    return resolutions
