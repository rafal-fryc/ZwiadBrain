"""Shared bill-id parser.

``bill.id`` is ``"{congress}-{type}-{number}"`` where ``<type>`` may itself
contain no hyphens (hr, s, hjres, sjres, hconres, sconres, hres, sres).
Congress is always an integer and number is always the trailing segment, so we
split on the FIRST and LAST hyphen to stay robust against multi-character types.

This is the single hardened parser for the whole project: ``leg_history`` and
the CLI both call it.  A malformed id is a configuration/data error, so it
raises :class:`ConfigError` (an :class:`AppError`) rather than a bare
``ValueError`` that would escape the CLI's ``except AppError`` boundary.
"""

from __future__ import annotations

import re

from zwiadbrain.exceptions import ConfigError


def parse_bill_id(bill_id: str) -> tuple[int, str, str]:
    """Parse ``bill.id`` into ``(congress: int, bill_type: str, number: str)``.

    Example::

        parse_bill_id("118-hr-9020")   # -> (118, "hr", "9020")
        parse_bill_id("118-hjres-45")  # -> (118, "hjres", "45")

    Raises :class:`ConfigError` when *bill_id* does not have three
    hyphen-separated segments, or when the congress segment is not an integer.
    """
    first_dash = bill_id.find("-")
    last_dash = bill_id.rfind("-")
    if first_dash == -1 or first_dash == last_dash:
        raise ConfigError(
            f"bill.id must be '<congress>-<type>-<number>', got: {bill_id!r}"
        )
    bill_type = bill_id[first_dash + 1 : last_dash]
    number = bill_id[last_dash + 1 :]
    if not bill_type or not number:
        raise ConfigError(
            f"bill.id must be '<congress>-<type>-<number>', got: {bill_id!r}"
        )
    try:
        congress = int(bill_id[:first_dash])
    except ValueError as exc:
        raise ConfigError(
            f"bill.id congress segment must be an integer, got: {bill_id!r}"
        ) from exc
    return congress, bill_type, number


# A bill number is a non-digit-run prefix followed by a trailing run of digits.
# Lazy prefix + anchored trailing \d+ partitions losslessly: prefix + digits == input.
# Special sessions (e.g. CA "SBX12") split to ("SBX", "12") — deterministic and unique
# within a (state, year) pair even though it does not segment the X-marker (D48).
_BILL_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")


def _split_bill_number(raw: str) -> tuple[str, str]:
    """Split a LegiScan bill number into (prefix, number) with leading zeros stripped.

    Raises :class:`ConfigError` when *raw* has no trailing digit run (e.g. a letter
    suffix), so a malformed number is a surfaced data error rather than a bad id.
    """
    match = _BILL_NUMBER_RE.match(raw.strip())
    if match is None or not match.group(1):
        raise ConfigError(f"state bill number must be <prefix><digits>, got: {raw!r}")
    prefix = match.group(1)
    number = match.group(2).lstrip("0") or "0"
    return prefix, number


def build_state_bill_id(state: str, year_start: int, bill_number: str) -> str:
    """Build a state bill's wiki id: ``{state}-{year_start}-{type}-{number}`` (D48).

    Globally unique (the state prefix and integer-leading federal ids never collide);
    lowercased; the type/number come from splitting the verbatim *bill_number*.
    """
    prefix, number = _split_bill_number(bill_number)
    return f"{state.lower()}-{year_start}-{prefix.lower()}-{number}"


def format_state_bill_number(bill_number: str) -> str:
    """Render a display bill number: uppercased prefix, a space, stripped-zero number."""
    prefix, number = _split_bill_number(bill_number)
    return f"{prefix.upper()} {number}"


# ---------------------------------------------------------------------------
# Enforcement-action identifiers (D53)
# ---------------------------------------------------------------------------

# Strong matter identifiers, tried highest-confidence first. Court dockets and FTC
# administrative dockets are unambiguous; the bare 7-digit FTC file number is the
# weakest (restricted to a "File No." context to avoid matching ZIPs/phone numbers).
_COURT_DOCKET_RE = re.compile(r"\b(\d{1,2}):(\d{2})-([a-z]{2,3})-(\d{3,6})\b", re.IGNORECASE)
_FTC_DOCKET_RE = re.compile(r"\b([CD])-(\d{3,4})\b")
_FTC_FILE_RE = re.compile(r"\bFile\s+No\.?\s*(\d{3}\s?\d{4})\b", re.IGNORECASE)


def parse_strong_key(text: str) -> str | None:
    """Extract a deterministic strong matter identifier from *text*, or None.

    Returns a lowercased, hyphen-normalized key suitable for an id segment:
    court docket ``2:25-cv-12295`` -> ``2-25-cv-12295``; FTC docket ``C-4790`` ->
    ``c-4790``; FTC file number ``2023155`` -> ``2023155``. None when nothing matches
    (the LLM-matcher path). Court dockets win over file numbers when both appear.
    """
    court = _COURT_DOCKET_RE.search(text)
    if court is not None:
        return "-".join(g.lower() for g in court.groups())
    ftc = _FTC_DOCKET_RE.search(text)
    if ftc is not None:
        return f"{ftc.group(1).lower()}-{ftc.group(2)}"
    file_no = _FTC_FILE_RE.search(text)
    if file_no is not None:
        return file_no.group(1).replace(" ", "")
    return None


# Corporate-suffix tokens stripped before slugging respondent names so that
# "Acme, Inc." and "Acme" produce the same id segment.
_CORP_SUFFIX_RE = re.compile(
    r"\b(inc|llc|corp|ltd|co|lp|llp|pllc|pc|pa)\b\.?",
    re.IGNORECASE,
)


def _slug(value: str) -> str:
    """Lowercase, strip corporate suffixes, keep alphanumerics, collapse other chars to hyphens."""
    cleaned = _CORP_SUFFIX_RE.sub(" ", value)
    out = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")
    return out or "unknown"


def build_enforcement_id(
    agency_slug: str,
    *,
    strong_key: str | None,
    respondent: str | None,
    year: int,
    existing_ids: frozenset[str] | set[str] = frozenset(),
) -> str:
    """Build a matter-stable, globally-unique enforcement page id (D53).

    With a strong key: ``{agency_slug}-{slug(strong_key)}``. Without: ``{agency_slug}-
    {year}-{slug(respondent)}``, with a numeric suffix appended on collision against
    *existing_ids* (two no-docket actions vs the same respondent in one year).
    """
    if strong_key:
        return f"{_slug(agency_slug)}-{_slug(strong_key)}"
    base = f"{_slug(agency_slug)}-{year}-{_slug(respondent or 'unknown')}"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"
