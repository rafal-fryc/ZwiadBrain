"""Legislative history assembler: deterministic spine + research leads.

Two entry points:

* :func:`assemble_spine` -- builds the *deterministic* :class:`LegHistory` from
  verified, machine-readable sources (Congress.gov actions, GovInfo CRPT/PLAW/CREC
  records, bill text versions).  Fields that require researcher judgment
  (``hearings``, ``statements``, ``conference``, ``narrative``) are left at their
  model defaults.

* :func:`collect_leads` -- returns a JSON-serializable dict of research leads for
  the researcher subagent.  Hearings here are *unverified leads* from a GovInfo
  full-text search; they are NOT inserted into the spine.  The researcher and
  grounding gate in later tasks decide what persists.

* :func:`ground_items` -- deterministic grounding gate for statements and hearings.
  Statements must pass URL resolution, quote-presence, and independent verifier
  checks.  Hearings must pass URL resolution.  Anything that fails is dropped and
  recorded in :class:`GroundingResult`.dropped; nothing is silently persisted.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from bs4 import BeautifulSoup, Comment
from pydantic import ValidationError

from zwiadbrain.models import (
    Bill,
    CommitteeReport,
    Enactment,
    FloorAction,
    Hearing,
    LegHistory,
    RelatedMedia,
    Statement,
    Vote,
)
from zwiadbrain.pipeline.ids import parse_bill_id

# ---------------------------------------------------------------------------
# Grounding gate result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DroppedItem:
    """Records a statement, hearing, or media item rejected by a grounding gate."""

    kind: Literal["statement", "hearing", "media"]
    identifier: str  # human-readable: "<speaker>: <first ~50 chars>", hearing/media title
    reason: str


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of :func:`ground_items`: kept items and everything rejected with reasons.

    Fields are tuples (not lists) so the result is truly immutable at this trust
    boundary: ``frozen=True`` prevents rebinding the attributes, but a list field
    would still permit ``result.statements.append(...)``, which must never be able
    to slip an unverified statement past the gate.  Tuples close that hole.
    """

    statements: tuple[Statement, ...] = field(default_factory=tuple)
    hearings: tuple[Hearing, ...] = field(default_factory=tuple)
    dropped: tuple[DroppedItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RelatedGroundingResult:
    """Outcome of :func:`ground_related`: kept Tier-2 media and everything rejected.

    Separate from :class:`GroundingResult` so the Tier-1 quote gate (``ground_items``)
    stays untouched.  ``media`` is a tuple for the same immutability reason
    :class:`GroundingResult` uses tuples: a list field would let an unconfirmed media
    item be appended past the gate.
    """

    media: tuple[RelatedMedia, ...] = field(default_factory=tuple)
    dropped: tuple[DroppedItem, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Structural protocols (allow fakes in tests without inheriting concrete classes)
# ---------------------------------------------------------------------------


class _CongressLike(Protocol):
    """Structural interface: the recorded-votes slice of CongressSource."""

    def recorded_votes(self, native_id: str) -> list[Vote]:
        ...


class _GovInfoLike(Protocol):
    """Structural interface: the leg-history slice of GovInfoSource.

    *number* is typed as ``str`` here because ``parse_bill_id`` always returns a
    ``str``; the concrete ``GovInfoSource`` accepts ``str | int``, which is a
    wider supertype and satisfies contravariance.
    """

    def committee_reports(
        self, congress: int, bill_type: str, number: str
    ) -> list[CommitteeReport]:
        ...

    def enacted_law(
        self, congress: int, bill_type: str, number: str
    ) -> Enactment | None:
        ...

    def hearings(self, congress: int, citation: str) -> list[Hearing]:
        ...

    def record_references(self, congress: int, citation: str) -> list[FloorAction]:
        ...


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _signed_date(bill: Bill) -> dt.date | None:
    """Scan bill actions for the presidential signing date.

    Prefers an action whose text contains ``"Signed by President"`` (the
    canonical signing event) over ``"Became Public Law"`` (the enrollment
    completion event, which may be dated a day or more later).  Both matches
    are case-insensitive.  Actions are oldest-first, so the first
    "signed by president" match is the canonical signing event.  Returns
    ``None`` when neither action is found.
    """
    signed: dt.date | None = None
    became_law: dt.date | None = None
    for action in bill.actions:
        text_lower = action.text.lower()
        if "signed by president" in text_lower:
            signed = action.date
            break
        if "became public law" in text_lower and became_law is None:
            became_law = action.date
    return signed if signed is not None else became_law


# ---------------------------------------------------------------------------
# Grounding gate helpers
# ---------------------------------------------------------------------------

# Minimum length (in normalized characters) a quote must have to be reliably
# grounded.  Very short strings (e.g. "no", "the AI Act") substring-match almost
# any page, which is a real false-accept vector for misattribution.  Quotes whose
# normalized form is shorter than this are dropped before any fetch.
_MIN_QUOTE_CHARS = 20

# Mapping from curly/typographic quote codepoints to their plain ASCII equivalents.
# Codepoints are listed as integer literals to avoid any source-file encoding
# dependency on non-ASCII characters in this module:
#   0x201C = LEFT DOUBLE QUOTATION MARK
#   0x201D = RIGHT DOUBLE QUOTATION MARK
#   0x2018 = LEFT SINGLE QUOTATION MARK
#   0x2019 = RIGHT SINGLE QUOTATION MARK
#   0x0060 = GRAVE ACCENT (backtick)
_CURLY_QUOTE_TABLE: dict[int, int] = {
    0x201C: ord('"'),
    0x201D: ord('"'),
    0x2018: ord("'"),
    0x2019: ord("'"),
    0x0060: ord("'"),
}


def _normalize_text(s: str) -> str:
    """Normalize a string for quote-presence comparison.

    Steps (applied to BOTH the quote and the page text):

    1. Replace curly double/single quotes and apostrophes with their straight
       ASCII equivalents (U+201C/201D -> double-quote, U+2018/2019/0060 -> apostrophe).
    2. Collapse all whitespace runs (spaces, tabs, newlines) to a single space
       and strip leading/trailing whitespace.
    """
    s = s.translate(_CURLY_QUOTE_TABLE)
    return " ".join(s.split())


def _page_text(page: str) -> str:
    """Extract human-visible text from an HTML page for quote-presence comparison.

    HTML byte-substring matching over-rejects on JS-rendered press-release pages
    and CREC pages where the quote sits across tag boundaries (e.g. a ``<br/>``
    split, a ``<span>`` wrapper, or an inline ``&nbsp;``).  BeautifulSoup's
    ``get_text(separator=' ')`` walks the parsed DOM and returns a single string
    with tag boundaries replaced by spaces; downstream
    :func:`_normalize_text` then collapses runs of whitespace, so a quote
    fragmented across markup matches as long as its WORDS appear in order.

    NOTE on the trust boundary: this raises recall (more true-positives) without
    lowering precision — the deterministic gate still requires the exact
    normalized quote to appear in the extracted text, and the cross-modal
    verifier subagent independently checks speaker attribution.  A
    misattributed-but-present quote is therefore kept by this gate and dropped
    by the verifier, by design.

    Text inside ``<script>``, ``<style>``, ``<noscript>``, and ``<template>``
    elements, and inside HTML comments, is removed before extraction: it is not
    human-visible, so a quote found only there is a false-positive against the
    verbatim-presence gate (D36) and must not ground a statement.
    """
    soup = BeautifulSoup(page, "html.parser")
    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    return soup.get_text(separator=" ")


def _quote_present(quote: str, page_text: str) -> bool:
    """Return True when *quote* appears (after normalization) inside *page_text*.

    *page_text* is treated as HTML and extracted to plain text before
    normalization; see :func:`_page_text`.  An empty or blank-only *quote*
    always returns False — an empty string must not be treated as matching.
    The comparison is case-sensitive: attributed quotes must match the source
    verbatim.
    """
    normalized_quote = _normalize_text(quote)
    if not normalized_quote:
        return False
    return normalized_quote in _normalize_text(_page_text(page_text))


def _statement_identifier(statement: Statement) -> str:
    """Short human-readable id for a statement in dropped-item records."""
    return f"{statement.speaker}: {statement.quote[:50]}"


def ground_items(
    statements: list[Statement],
    hearings: list[Hearing],
    *,
    fetch: Callable[[str], tuple[int, str]],
    verifier_verdicts: dict[int, bool],
) -> GroundingResult:
    """Run the deterministic grounding gate over *statements* and *hearings*.

    **Contract for** *fetch*: ``fetch(url) -> (status_code, page_text)``.  It
    never raises for HTTP/network problems; it returns ``0`` as the status when
    the host is unreachable and ``""`` as the page text when unavailable.  No
    real network I/O is performed inside this function.

    **Ordering contract for** *verifier_verdicts*: this dict is keyed by each
    statement's index in THIS *statements* list.  The caller MUST pass
    *statements* in the exact order the verifier verdicts were computed for --
    reordering between verification and this call would silently apply a verdict
    to the wrong statement, i.e. misattribute a quote (the highest-stakes failure
    mode in the project).

    **Statement gate** (all must pass, first failure is the recorded reason):

    0. Normalized quote length must be >= ``_MIN_QUOTE_CHARS``; if shorter ->
       drop with reason ``"quote too short to reliably ground ({len} chars)"``.
       This runs BEFORE any fetch: a trivially-short quote substring-matches
       almost any page and is a false-accept (misattribution) vector.
    1. ``status, text = fetch(statement.source_url)``; if ``status != 200`` ->
       drop with reason ``"source url returned status {status}"``.
    2. Quote must be present in *text* (via :func:`_quote_present`); if not ->
       drop with reason ``"quote not found on source page"``.
    3. ``verifier_verdicts.get(i, False)`` must be True (a missing index counts
       as not-verified); if False -> drop with reason
       ``"verifier did not confirm the quote"``.
    4. Else -> keep, appending ``statement.model_copy(update={"verified": True})``.

    **Hearing gate**:

    * No ``url`` -> drop with reason ``"hearing has no source url"``.
    * ``fetch(hearing.url)`` returns ``status != 200`` -> drop with reason
      ``"hearing url returned status {status}"``.
    * Else -> keep unchanged.

    Returns a :class:`GroundingResult` whose ``statements`` (each with
    ``verified=True``), ``hearings`` (unchanged), and ``dropped`` are tuples --
    immutable, so nothing can be appended past the gate.
    """
    kept_statements: list[Statement] = []
    kept_hearings: list[Hearing] = []
    dropped: list[DroppedItem] = []

    # verifier_verdicts is keyed by each statement's index in THIS `statements`
    # list; the caller MUST pass `statements` in the exact order the verifier
    # verdicts were computed for -- reordering between verification and this call
    # would silently apply a verdict to the wrong statement (misattribution).
    for i, stmt in enumerate(statements):
        identifier = _statement_identifier(stmt)
        # Gate 0: minimum normalized quote length (runs before any fetch).
        normalized_quote = _normalize_text(stmt.quote)
        if len(normalized_quote) < _MIN_QUOTE_CHARS:
            dropped.append(
                DroppedItem(
                    kind="statement",
                    identifier=identifier,
                    reason=f"quote too short to reliably ground ({len(normalized_quote)} chars)",
                )
            )
            continue
        status, text = fetch(stmt.source_url)
        if status != 200:
            dropped.append(
                DroppedItem(
                    kind="statement",
                    identifier=identifier,
                    reason=f"source url returned status {status}",
                )
            )
            continue
        if not _quote_present(stmt.quote, text):
            dropped.append(
                DroppedItem(
                    kind="statement",
                    identifier=identifier,
                    reason="quote not found on source page",
                )
            )
            continue
        if not verifier_verdicts.get(i, False):
            dropped.append(
                DroppedItem(
                    kind="statement",
                    identifier=identifier,
                    reason="verifier did not confirm the quote",
                )
            )
            continue
        kept_statements.append(stmt.model_copy(update={"verified": True}))

    for hearing in hearings:
        if not hearing.url:
            dropped.append(
                DroppedItem(
                    kind="hearing",
                    identifier=hearing.title,
                    reason="hearing has no source url",
                )
            )
            continue
        status, _ = fetch(hearing.url)
        if status != 200:
            dropped.append(
                DroppedItem(
                    kind="hearing",
                    identifier=hearing.title,
                    reason=f"hearing url returned status {status}",
                )
            )
            continue
        kept_hearings.append(hearing)

    return GroundingResult(
        statements=tuple(kept_statements),
        hearings=tuple(kept_hearings),
        dropped=tuple(dropped),
    )


def ground_related(
    related_media: list[RelatedMedia],
    *,
    fetch: Callable[[str], tuple[int, str]],
    verifier_verdicts: dict[int, bool],
) -> RelatedGroundingResult:
    """Run the Tier-2 grounding gate over *related_media* (D69 Phase B).

    Tier-2 media carries NO attributed quote, so there is nothing to misattribute
    and the verbatim-quote gate does not apply.  Each item must pass two checks,
    first failure recorded:

    1. ``status, _ = fetch(media.url)``; if ``status != 200`` -> drop with reason
       ``"media url returned status {status}"``.  ``RelatedMedia.url`` is required
       and http-validated by the model, so there is no separate "no url" branch
       (unlike the hearing gate, whose ``url`` is optional).
    2. ``verifier_verdicts.get(i, False)`` must be True — an independent verifier
       *identity* confirmation that the link is the claimed hearing video / page.
       A missing index counts as not-confirmed; drop with reason
       ``"verifier did not confirm the media"``.

    **Ordering contract for** *verifier_verdicts*: keyed by each media item's index
    in THIS list (same enumerate contract as :func:`ground_items`).  Kept items are
    returned UNCHANGED — there is no ``verified`` flag to set; membership of the kept
    tuple is itself the confirmation.

    The gate logic for :func:`ground_items`, :func:`_normalize_text`, and the
    quote-presence path is intentionally untouched by this function.
    """
    kept_media: list[RelatedMedia] = []
    dropped: list[DroppedItem] = []

    for i, media in enumerate(related_media):
        status, _ = fetch(media.url)
        if status != 200:
            dropped.append(
                DroppedItem(
                    kind="media",
                    identifier=media.title,
                    reason=f"media url returned status {status}",
                )
            )
            continue
        if not verifier_verdicts.get(i, False):
            dropped.append(
                DroppedItem(
                    kind="media",
                    identifier=media.title,
                    reason="verifier did not confirm the media",
                )
            )
            continue
        kept_media.append(media)

    return RelatedGroundingResult(
        media=tuple(kept_media),
        dropped=tuple(dropped),
    )


# ---------------------------------------------------------------------------
# Lane merge (PHASE-15 / D74) — shared by build-verifier-input + assemble-leg-history-input
# ---------------------------------------------------------------------------

# Canonical fan-out lane order.  The merged statement / hearing / media order is fixed by
# THIS tuple, never by the caller's dict order, so the verifier (dispatched over the
# build-verifier-input merge) and the assembler (which re-merges) agree on every index.
LANE_ORDER: tuple[str, ...] = ("crec", "hearings", "press", "signing")


@dataclass(frozen=True)
class MergedResearch:
    """Deterministic merge of the four researcher lane outputs (PHASE-15 / D74).

    Produced by :func:`merge_lanes` and consumed by BOTH the ``build-verifier-input`` and
    ``assemble-leg-history-input`` CLI steps.  The merge is pure and deterministic, so
    calling it on the same lane inputs on either side of the verifier yields byte-identical
    statement / media order — the verifier's echoed indices therefore align with the
    assembler's positions by construction, not by hand.

    Tuples (not lists) for the same trust-boundary immutability reason
    :class:`GroundingResult` uses them.
    """

    statements: tuple[Statement, ...] = field(default_factory=tuple)
    hearings: tuple[Hearing, ...] = field(default_factory=tuple)
    related_media: tuple[RelatedMedia, ...] = field(default_factory=tuple)
    narrative: str | None = None
    dropped_lanes: tuple[str, ...] = field(default_factory=tuple)
    parse_dropped: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _lane_items(payload: dict[str, object], key: str) -> list[object] | None:
    """Return the list at *key* in a lane payload, or ``None`` if the field is malformed.

    A missing or ``null`` field becomes an empty list (a lane legitimately produces nothing
    in a category).  A present-but-non-list field means the lane's JSON is structurally
    broken at the top level; returning ``None`` signals the caller to drop the whole lane.
    """
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    return items


def merge_lanes(lanes: Mapping[str, object | None]) -> MergedResearch:
    """Merge the four researcher lane payloads into one deterministic research set.

    *lanes* maps a lane name (``crec`` / ``hearings`` / ``press`` / ``signing``) to that
    lane's loaded JSON object, or ``None`` when the lane file was missing / unreadable.
    Lanes are processed in :data:`LANE_ORDER` (NOT input dict order), so the merged
    statement / media order is stable regardless of how the caller built the mapping.

    Merge rules:

    * **statements** — concatenated across lanes; deduped by ``(speaker, quote)`` (first
      occurrence wins).
    * **hearings** — concatenated; deduped by ``url`` (first wins).  Url-less hearings are
      NEVER deduped against each other (a missing url is not an identity) — they are kept and
      left for the render gate to drop with a per-item audit line.
    * **related_media** — concatenated; deduped by ``url`` (first wins; ``url`` is required
      by the model).
    * **narrative** — taken ONLY from the ``crec`` lane (the sole lane that writes one);
      ``None`` when that lane is absent or its narrative is blank.

    Failure handling:

    * A lane whose payload is ``None`` or not a JSON object, or whose ``statements`` /
      ``hearings`` / ``related_media`` field is present-but-not-a-list (or whose
      ``narrative`` is present-but-not-a-string), is dropped whole and recorded in
      ``dropped_lanes`` (mirrors the orchestrator's "drop just that lane" rule).
    * An individual item that fails model validation is parse-dropped (recorded in
      ``parse_dropped`` as ``(identifier, reason)``) without dropping the rest of its lane,
      mirroring render-leg-history's per-item parse-drop.

    No I/O and no LLM calls: pure deterministic plumbing.
    """
    statements: list[Statement] = []
    hearings: list[Hearing] = []
    related_media: list[RelatedMedia] = []
    dropped_lanes: list[str] = []
    parse_dropped: list[tuple[str, str]] = []

    seen_statements: set[tuple[str, str]] = set()
    seen_hearing_urls: set[str] = set()
    seen_media_urls: set[str] = set()

    narrative: str | None = None

    for lane in LANE_ORDER:
        payload = lanes.get(lane)
        if not isinstance(payload, dict):
            # None (unreadable file) or a non-object top level -> drop the whole lane.
            dropped_lanes.append(lane)
            continue
        lane_payload: dict[str, object] = payload  # pyright: ignore[reportUnknownVariableType]

        stmt_items = _lane_items(lane_payload, "statements")
        hearing_items = _lane_items(lane_payload, "hearings")
        media_items = _lane_items(lane_payload, "related_media")
        narrative_raw = lane_payload.get("narrative")
        if (
            stmt_items is None
            or hearing_items is None
            or media_items is None
            or (narrative_raw is not None and not isinstance(narrative_raw, str))
        ):
            dropped_lanes.append(lane)
            continue

        for i, item in enumerate(stmt_items):
            try:
                stmt = Statement.model_validate(item)
            except ValidationError as exc:
                parse_dropped.append((f"{lane} statement[{i}]", str(exc)))
                continue
            key = (stmt.speaker, stmt.quote)
            if key in seen_statements:
                continue
            seen_statements.add(key)
            statements.append(stmt)

        for i, item in enumerate(hearing_items):
            try:
                hearing = Hearing.model_validate(item)
            except ValidationError as exc:
                parse_dropped.append((f"{lane} hearing[{i}]", str(exc)))
                continue
            if hearing.url:
                if hearing.url in seen_hearing_urls:
                    continue
                seen_hearing_urls.add(hearing.url)
            hearings.append(hearing)

        for i, item in enumerate(media_items):
            try:
                media = RelatedMedia.model_validate(item)
            except ValidationError as exc:
                parse_dropped.append((f"{lane} related_media[{i}]", str(exc)))
                continue
            if media.url in seen_media_urls:
                continue
            seen_media_urls.add(media.url)
            related_media.append(media)

        if lane == "crec" and isinstance(narrative_raw, str) and narrative_raw.strip():
            narrative = narrative_raw

    return MergedResearch(
        statements=tuple(statements),
        hearings=tuple(hearings),
        related_media=tuple(related_media),
        narrative=narrative,
        dropped_lanes=tuple(dropped_lanes),
        parse_dropped=tuple(parse_dropped),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assemble_spine(
    bill: Bill,
    congress_source: _CongressLike,
    govinfo_source: _GovInfoLike,
) -> LegHistory:
    """Build and return a :class:`LegHistory` with the deterministic spine populated.

    Fields populated:

    * ``versions`` -- from ``bill.text_versions``
    * ``committee_reports`` -- from GovInfo CRPT related records
    * ``votes`` -- from Congress.gov recorded votes on the bill's actions
    * ``floor_consideration`` -- from GovInfo CREC search (verifiable package URLs)
    * ``enactment`` -- merged from GovInfo PLAW record + bill action dates + bill.public_law

    Fields left at defaults (researcher's job in later tasks):
    ``conference``, ``narrative``, ``hearings``, ``statements``.

    *congress_source* and *govinfo_source* are accepted structurally (Protocol),
    so tests may pass lightweight fakes without subclassing the concrete clients.
    """
    congress, bill_type, number = parse_bill_id(bill.id)
    native_id = f"{congress}/{bill_type}/{number}"
    citation = bill.bill_number

    # Deterministic spine fields
    committee_reports = govinfo_source.committee_reports(congress, bill_type, number)
    votes = congress_source.recorded_votes(native_id)
    # Filter to URL-bearing items only: a CREC hit with no url is just a title and cannot
    # be verified — matching the hearings/statements no-link-no-persist policy.
    floor_consideration = [
        f for f in govinfo_source.record_references(congress, citation) if f.url
    ]

    # Enactment: merge GovInfo PLAW record with action-scanned signed date + bill fallback
    law = govinfo_source.enacted_law(congress, bill_type, number)
    signed = _signed_date(bill)

    # Build the enactment object only when there is something concrete to record.
    # Prefer govinfo values; fall back to bill.public_law when govinfo returned nothing.
    public_law = (law.public_law if law and law.public_law else None) or bill.public_law
    statutes = law.statutes_at_large if law else None
    # URL backstop: prefer GovInfo PLAW url; when absent, fall back to the bill's
    # Congress.gov page URL so the enactment row always has a clickable source link.
    # CongressSource always populates sources["Congress.gov"] on enriched bills.
    url = (law.url if law and law.url else None) or bill.sources.get("Congress.gov")

    enactment: Enactment | None
    if public_law or signed or url or statutes:
        enactment = Enactment(
            date_signed=signed,
            public_law=public_law,
            statutes_at_large=statutes,
            url=url,
        )
    else:
        enactment = None

    return LegHistory(
        versions=bill.text_versions,
        committee_reports=committee_reports,
        votes=votes,
        floor_consideration=floor_consideration,
        enactment=enactment,
        # researcher fields -- left at defaults
        conference=None,
        narrative=None,
        hearings=[],
        statements=[],
    )


def collect_leads(
    bill: Bill,
    govinfo_source: _GovInfoLike,
) -> dict[str, Any]:
    """Return a JSON-serializable dict of research leads for the researcher subagent.

    Hearings are unverified leads from a GovInfo full-text search.  They are NOT
    inserted into the spine; the researcher + grounding gate in later tasks decide
    what persists.  Dates are serialized as ISO-format strings when present, else
    ``None``.

    *govinfo_source* is accepted structurally (Protocol), so tests may pass
    lightweight fakes without subclassing the concrete client.
    """
    congress, _, _ = parse_bill_id(bill.id)
    citation = bill.bill_number

    hearings = govinfo_source.hearings(congress, citation)
    hearing_dicts = [h.model_dump(mode="json", exclude_none=True) for h in hearings]

    return {
        "id": bill.id,
        "congress": str(congress),
        "citation": citation,
        "title": bill.title,
        "sponsors": bill.sponsors,
        "related_bills": bill.related_bills,
        "introduced_date": bill.introduced_date.isoformat() if bill.introduced_date else None,
        "latest_action_date": (
            bill.latest_action_date.isoformat() if bill.latest_action_date else None
        ),
        "hearings": hearing_dicts,
    }
