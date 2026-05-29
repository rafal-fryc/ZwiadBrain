"""Pure key-extraction for law-brain commentary matching (PHASE-09).

Both halves of a match are projected into one jurisdiction-qualified string
key space, so a match is a plain set intersection:
``page_keys(page) & tracked_item_keys(item)``. Nothing here does I/O.

Three key families:

* ``"{NORMJURIS}::bill::{PREFIX}-{N}"`` — a legislative bill, e.g.
  ``"US-CA::bill::SB-53"`` or ``"US::bill::HR-8818"`` (after ``US-Federal``
  -> ``US`` normalization). ``PREFIX`` is an uppercased recognized bill-type
  token; ``N`` is the bill number with leading zeros stripped.
* ``"docket::{key}"`` — a court/agency docket, extracted by the single hardened
  :func:`zwiadbrain.pipeline.ids.parse_strong_key` (reused, never re-implemented).
* ``"public_law::{N}"`` — an enacted public law, e.g. ``"public_law::119-12"``;
  the cross-type bridge between a statute page and an enforcement page (D59).

Fail-closed (D60): a page whose slug carries a multi-subject marker
(``tracker``/``landscape``/``map``/``scholarship``) emits **zero** keys — it
has no single subject, so it neither mints nor attaches commentary. Bill/docket
extraction is also anchored tightly enough that an academic reporter citation
(``103 Calif. L. Rev. 513``) is never misread as a bill key.
"""

from __future__ import annotations

import hashlib
import re

from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.pipeline.ids import parse_strong_key
from zwiadbrain.sources.lawbrain import LawBrainPage

# Recognized legislative bill-type prefixes (federal + state). The alternation
# is built longest-first so "HJRES" matches before "H", "SB" before "S", etc.
# Each prefix is expanded with optional internal ``[.\s]*`` so "H.R." / "H R" /
# "HR" all match the same token. The whole match is word-boundary anchored on
# the left so "Calif. L. Rev. 513" can't trigger "S" (the char preceding "S"
# in "Stats" or the last letter before a space is always a word-char, not a
# boundary). The right side is anchored by the mandatory digits run + ``\b``.
_BILL_PREFIXES: tuple[str, ...] = (
    "HJRES",
    "SJRES",
    "HCONRES",
    "SCONRES",
    "HRES",
    "SRES",
    "HR",
    "SB",
    "HB",
    "AB",
    "SCR",
    "HCR",
    "ACR",
    "SR",
    "S",
    "H",
)


def _build_bill_re() -> re.Pattern[str]:
    """Build the bill-reference regex from the ordered prefix list.

    Each prefix letter sequence is joined with ``[.\\s]*`` so "H.R.", "H R",
    "HR" all match.  The alternation is longest-first to avoid "S" eating "SB".
    The whole pattern is word-boundary anchored on the left (``\\b``) and the
    number run is digit-boundary anchored on the right (``\\b``).
    """
    alt = "|".join(
        r"[.\s]*".join(ch for ch in prefix) for prefix in _BILL_PREFIXES
    )
    return re.compile(
        r"\b(" + alt + r")[.\s]*0*(\d+)\b",
        re.IGNORECASE,
    )


_BILL_RE: re.Pattern[str] = _build_bill_re()

# A public-law citation: "Pub. L. 119-12", "Public Law 119-12", "P.L. 119-12".
_PUBLIC_LAW_RE: re.Pattern[str] = re.compile(
    r"\b(?:pub(?:lic)?\.?\s*l(?:aw)?\.?)\s*(\d+-\d+)\b",
    re.IGNORECASE,
)


def normalize_jurisdiction(j: str) -> str:
    """Map a law-brain jurisdiction onto the ZwiadBrain code space.

    ``US-Federal`` -> ``US``; every other value (``US-CA``, ``US`` …) passes
    through unchanged.
    """
    return "US" if j == "US-Federal" else j


def _normalize_bill_prefix(raw: str) -> str:
    """Strip internal dots/spaces and uppercase a matched bill-type token."""
    return re.sub(r"[.\s]", "", raw).upper()


def _bill_keys_from_text(text: str, normjuris: str) -> set[str]:
    """Extract ``{normjuris}::bill::{PREFIX}-{N}`` keys from *text*.

    Uses the shared :data:`_BILL_RE`; leading zeros in the number are stripped.
    """
    keys: set[str] = set()
    for match in _BILL_RE.finditer(text):
        prefix = _normalize_bill_prefix(match.group(1))
        number = match.group(2).lstrip("0") or "0"
        keys.add(f"{normjuris}::bill::{prefix}-{number}")
    return keys


def _bill_key_from_number(bill_number: str, normjuris: str) -> str | None:
    """Project a tracked ``bill_number`` ("SB 53", "H.R. 8818") into one bill key.

    Searches (not fullmatch) so surrounding context (e.g. a title field) still
    works.  Returns ``None`` when *bill_number* does not contain a recognized
    ``<prefix><digits>`` pattern.
    """
    match = _BILL_RE.search(bill_number)
    if match is None:
        return None
    prefix = _normalize_bill_prefix(match.group(1))
    number = match.group(2).lstrip("0") or "0"
    return f"{normjuris}::bill::{prefix}-{number}"


def page_keys(page: LawBrainPage, slug_markers: list[str]) -> set[str]:
    """Extract jurisdiction-qualified match keys from a law-brain *page*.

    Returns an empty set (fail-closed, D60) when any *slug_markers* entry is a
    substring of ``page.slug`` — a multi-subject tracker/landscape/map/
    scholarship page has no single subject and must neither mint nor attach.

    Otherwise scans slug + title + citation + each tag for bill, docket, and
    public-law references. Bill keys are qualified by the page's normalized
    jurisdiction (the first listed); docket and public_law keys are
    jurisdiction-agnostic identifiers.
    """
    if any(marker in page.slug for marker in slug_markers):
        return set()

    keys: set[str] = set()
    text_fields = [page.slug, page.title, page.citation or "", *page.tags]
    blob = "\n".join(text_fields)

    # Bill keys need the page's jurisdiction; use the first listed (normalized).
    normjuris = normalize_jurisdiction(page.jurisdiction[0]) if page.jurisdiction else ""
    if normjuris:
        keys |= _bill_keys_from_text(blob, normjuris)

    docket = parse_strong_key(blob)
    if docket is not None:
        keys.add(f"docket::{docket}")

    for m in _PUBLIC_LAW_RE.finditer(blob):
        keys.add(f"public_law::{m.group(1)}")

    return keys


def tracked_item_keys(item: Bill | EnforcementAction) -> set[str]:
    """Project a tracked ZwiadBrain item into the same key space as :func:`page_keys`.

    A ``Bill`` yields a single ``{normjuris}::bill::{PREFIX}-{N}`` key from its
    ``bill_number``. An ``EnforcementAction`` yields ``docket::{key}`` from its
    ``docket`` (via :func:`~zwiadbrain.pipeline.ids.parse_strong_key`) and a
    ``public_law::{N}`` key for each statute that parses as a public-law
    citation — the cross-type bridge (D59).
    """
    keys: set[str] = set()
    if isinstance(item, Bill):
        normjuris = normalize_jurisdiction(item.jurisdiction)
        key = _bill_key_from_number(item.bill_number, normjuris)
        if key is not None:
            keys.add(key)
        return keys

    # EnforcementAction branch
    if item.docket:
        docket = parse_strong_key(item.docket)
        if docket is not None:
            keys.add(f"docket::{docket}")
    for statute in item.statutes:
        m = _PUBLIC_LAW_RE.search(statute)
        if m is not None:
            keys.add(f"public_law::{m.group(1)}")
    return keys


def keys_hash(keys: set[str]) -> str:
    """SHA-256 over the sorted, newline-joined key set (D9 stickiness cursor).

    Order-independent: ``keys_hash({"a", "b"}) == keys_hash({"b", "a"})``. Used
    by the link registry to detect when a settled page's extracted keys change.
    """
    joined = "\n".join(sorted(keys))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
