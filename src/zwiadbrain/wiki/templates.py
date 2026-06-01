"""Markdown page-body builders for bill and enforcement wiki pages.

A single jinja2 template renders a pre-built, already-filtered list of
``{heading, body}`` sections, so output is deterministic. Section content
(timeline, amendments, legislative history, copied commentary) is assembled by
the typed helpers below; empty sections are dropped by the callers.
"""

import datetime as dt
import re

import jinja2

from zwiadbrain.models import (
    Action,
    Amendment,
    Bill,
    CommentarySource,
    Enactment,
    EnforcementAction,
    EnforcementDevelopment,
    FloorAction,
    Hearing,
    LegHistory,
    Statement,
    TextVersion,
    Vote,
)

_env = jinja2.Environment(
    autoescape=False,
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
)

# One generic body template: a filtered list of {heading, body} sections.
_BODY = _env.from_string(
    "{% for s in sections %}## {{ s.heading }}\n\n{{ s.body }}\n"
    "{% if not loop.last %}\n{% endif %}{% endfor %}"
)

_COMMENTARY_NOTE = (
    "Copied verbatim. Law brain authoritative for analysis; official sources "
    "authoritative for bill text and legislative history."
)

LAWBRAIN_REGION_BEGIN = "<!-- lawbrain:region:begin -->"
LAWBRAIN_REGION_END = "<!-- lawbrain:region:end -->"


def _demote_headings(text: str) -> str:
    """Demote ATX headings by one level (## -> ###) in copied commentary.

    Markdown has no h7, so the demotion is clamped at h6: an h1-h5 heading gains
    one ``#``, and an h6 heading is left at h6 (the ``{1,5}`` bound never matches
    a 6-hash run, so it cannot produce a 7-hash heading).
    """
    return re.sub(r"(?m)^(#{1,5})(?= )", r"#\1", text)


def _neutralize_wikilinks(text: str) -> str:
    """Strip dead ``[[wiki-slug]]`` cross-reference links to plain text.

    The law brain is a separate wiki: its ``[[...]]`` links resolve nowhere in
    this corpus, so copied commentary renders them as their inner text only.
    """
    return re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _timeline(actions: list[Action]) -> str:
    lines: list[str] = []
    for action in actions:
        prefix = f"{action.date.isoformat()} — " if action.date else ""
        suffix = f" _({action.chamber})_" if action.chamber else ""
        lines.append(f"- {prefix}{action.text}{suffix}")
    return "\n".join(lines)


def _amendments(amendments: list[Amendment]) -> str:
    lines: list[str] = []
    for amendment in amendments:
        bits = [f"**{amendment.number}**"]
        if amendment.sponsor:
            bits.append(amendment.sponsor)
        if amendment.status:
            bits.append(f"[{amendment.status}]")
        explanation = f": {amendment.what_changed}" if amendment.what_changed else ""
        lines.append(f"- {' — '.join(bits)}{explanation}")
    return "\n".join(lines)


def _text_versions(versions: list[TextVersion]) -> str:
    lines: list[str] = []
    for version in versions:
        date = f" ({version.date.isoformat()})" if version.date else ""
        label = f"[{version.code}]({version.url})" if version.url else version.code
        lines.append(f"- {label}{date}")
    return "\n".join(lines)


def _developments(developments: list[EnforcementDevelopment]) -> str:
    """Render the matter timeline, oldest first."""
    ordered = sorted(
        developments,
        key=lambda d: (d.date or dt.date.min, str(d.source_url)),
    )
    lines: list[str] = []
    for d in ordered:
        date = f"{d.date.isoformat()} — " if d.date else ""
        lines.append(f"- {date}{d.summary} — [source]({d.source_url})")
    return "\n".join(lines)


def _sources(sources: dict[str, str]) -> str:
    return "\n".join(f"- [{name}]({url})" for name, url in sorted(sources.items()))


def _floor_action_line(f: FloorAction) -> str:
    """Render one floor-consideration item, linking the CR citation when a url is present."""
    when: list[str] = []
    if f.date:
        when.append(f.date.isoformat())
    if f.chamber:
        when.append(f.chamber)
    prefix = " ".join(when)
    if f.url:
        cr_part = (
            f"[{f.congressional_record}]({f.url})"
            if f.congressional_record
            else f"[Congressional Record]({f.url})"
        )
    else:
        cr_part = f.congressional_record or ""
    segments = [seg for seg in (prefix, cr_part) if seg]
    return "- " + " — ".join(segments)


def _vote_line(v: Vote) -> str:
    """Render one vote item, appending a roll-call link when roll_call_url is present."""
    when: list[str] = []
    if v.date:
        when.append(v.date.isoformat())
    if v.chamber:
        when.append(v.chamber)
    base = " ".join(when)
    if v.result:
        base = f"{base}: {v.result}" if base else v.result
    if v.roll_call_url:
        roll_call = f"[roll call]({v.roll_call_url})"
        base = f"{base} — {roll_call}" if base else roll_call
    return f"- {base}"


def _enactment_block(enactment: Enactment) -> str:
    """Render the enactment bullet list, linking the public law when url is present."""
    rows: list[str] = []
    if enactment.date_signed:
        rows.append(f"Signed: {enactment.date_signed.isoformat()}")
    if enactment.url:
        if enactment.public_law:
            rows.append(f"Public Law: [{enactment.public_law}]({enactment.url})")
        else:
            rows.append(f"[Public law document]({enactment.url})")
    elif enactment.public_law:
        rows.append(f"Public Law: {enactment.public_law}")
    if enactment.statutes_at_large:
        s = enactment.statutes_at_large
        rows.append(f"Statutes at Large: [{s.citation}]({s.url})")
    return "\n".join(f"- {row}" for row in rows)


def _hearings_block(hearings: list[Hearing]) -> str:
    """Render hearings that have a url; skip any without one (not verifiable)."""
    lines: list[str] = []
    for h in hearings:
        if not h.url:
            continue
        bits: list[str] = [f'**Hearing:** "{h.title}"']
        meta: list[str] = []
        if h.committee:
            meta.append(h.committee)
        if h.date:
            meta.append(h.date.isoformat())
        if meta:
            bits.append(", ".join(meta))
        bits.append(f"[source]({h.url})")
        lines.append("- " + " — ".join(bits))
    return "\n".join(lines)


def _statements_block(statements: list[Statement]) -> str:
    """Render statements that have a source_url; skip any without one (not verifiable)."""
    lines: list[str] = []
    for s in statements:
        if not s.source_url:
            continue
        date_part = f", {s.date.isoformat()}" if s.date else ""
        base = f"- **{s.speaker}** ({s.role}){date_part} — \"{s.quote}\" — [source]({s.source_url})"
        if s.verified:
            base = f"{base} ✓"
        lines.append(base)
    return "\n".join(lines)


def _leg_history(history: LegHistory) -> str:
    parts: list[str] = []
    # 1. Legislative Journey (narrative)
    if history.narrative:
        parts.append("### Legislative Journey\n\n" + history.narrative.strip())
    # 2. Versions
    if history.versions:
        parts.append("### Versions\n\n" + _text_versions(history.versions))
    # 3. Committee Reports
    if history.committee_reports:
        reports = "\n".join(
            f"- [{r.citation}]({r.url})" if r.url else f"- {r.citation}"
            for r in history.committee_reports
        )
        parts.append("### Committee Reports\n\n" + reports)
    # 4. Hearings
    hearings_text = _hearings_block(history.hearings)
    if hearings_text:
        parts.append("### Hearings\n\n" + hearings_text)
    # 5. Floor Consideration
    if history.floor_consideration:
        floor = "\n".join(_floor_action_line(f) for f in history.floor_consideration)
        parts.append("### Floor Consideration\n\n" + floor)
    # 6. Votes
    if history.votes:
        votes = "\n".join(_vote_line(v) for v in history.votes)
        parts.append("### Votes\n\n" + votes)
    # 7. Conference
    if history.conference:
        parts.append("### Conference\n\n" + history.conference)
    # 8. Enactment
    if history.enactment:
        enactment_text = _enactment_block(history.enactment)
        if enactment_text:
            parts.append("### Enactment\n\n" + enactment_text)
    # 9. Statements
    statements_text = _statements_block(history.statements)
    if statements_text:
        parts.append("### Statements\n\n" + statements_text)
    return "\n\n".join(parts)


def _commentary_block(source: CommentarySource) -> str:
    updated = f" (updated {source.updated.isoformat()})" if source.updated else ""
    body = _neutralize_wikilinks(_demote_headings(source.body.strip())) if source.body else ""
    return "\n".join(
        [
            f"<!-- lawbrain:begin slug={source.slug} -->",
            f"> Source: law brain page `{source.slug}`{updated}.",
            f"> {_COMMENTARY_NOTE}",
            "",
            body,
            f"<!-- lawbrain:end slug={source.slug} -->",
        ]
    )


def _commentary(sources: list[CommentarySource]) -> str:
    return "\n\n".join(_commentary_block(s) for s in sorted(sources, key=lambda s: s.slug))


def _normalize_url(url: str) -> str:
    """Normalize a url for dedup: lowercase host, strip a single trailing slash."""
    match = re.match(r"^(https?://)([^/]+)(.*)$", url)
    if not match:
        return url.rstrip("/")
    scheme, host, rest = match.groups()
    return f"{scheme}{host.lower()}{rest}".rstrip("/")


def _link_host(url: str) -> str:
    """Return the lowercased host of a url, or the url itself when not http(s)."""
    match = re.match(r"^https?://([^/]+)", url)
    return match.group(1).lower() if match else url


def _further_reading(sources: list[CommentarySource]) -> str:
    """Aggregate and dedup ``Further Reading`` links across commentary sources.

    Dedup by normalized URL; first occurrence in slug order wins; emit the
    canonical (normalized) URL. The surviving link keeps the slug-first
    occurrence's anchor text but is rendered with the normalized URL (lower host,
    single trailing slash stripped), so output is canonical and D20-stable
    regardless of which raw URL variant appeared. Rows are sorted by
    ``(host, normalized_url)``.
    """
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []  # (anchor text, normalized url)
    for source in sorted(sources, key=lambda s: s.slug):
        for link in source.links:
            key = _normalize_url(link.url)
            if key in seen:
                continue
            seen.add(key)
            unique.append((link.text, key))
    unique.sort(key=lambda item: (_link_host(item[1]), item[1]))
    return "\n".join(f"- [{text}]({url})" for text, url in unique)


def _lawbrain_region(sources: list[CommentarySource]) -> str | None:
    """Render the marker-delimited law-brain region, or ``None`` if no sources.

    The region is the commentary blocks under ``## Commentary & Analysis`` plus,
    when any source carries links, a ``## Further Reading (via law brain)``
    section, wrapped between :data:`LAWBRAIN_REGION_BEGIN` and
    :data:`LAWBRAIN_REGION_END`. Callers append it last, after ``Sources``.
    """
    if not sources:
        return None
    parts = ["## Commentary & Analysis\n\n" + _commentary(sources)]
    further = _further_reading(sources)
    if further:
        parts.append("## Further Reading (via law brain)\n\n" + further)
    inner = "\n\n".join(parts)
    return f"{LAWBRAIN_REGION_BEGIN}\n{inner}\n{LAWBRAIN_REGION_END}"


def render_bill_body(bill: Bill) -> str:
    """Render the Markdown body for a bill page (no frontmatter).

    When ``bill.flipped_out`` is set, an HTML comment marker is prepended to the
    body for audit visibility in ``git log -p``.  The marker escapes two
    characters/sequences in the reason: ``-->`` (HTML comment terminator) is
    replaced with ``--&gt;``, and embedded double quotes are backslash-escaped,
    so the attribute stays well-formed even when the classifier emits prose
    containing either sequence.
    """
    sections: list[dict[str, str]] = []
    if bill.summary:
        sections.append({"heading": "Summary", "body": bill.summary.strip()})
    if bill.actions:
        sections.append({"heading": "Status & Timeline", "body": _timeline(bill.actions)})
    if bill.amendments:
        sections.append({"heading": "Amendments", "body": _amendments(bill.amendments)})
    if bill.leg_history:
        leg_history_body = _leg_history(bill.leg_history)
        if leg_history_body:
            sections.append({"heading": "Legislative History", "body": leg_history_body})
    if bill.text_versions:
        sections.append({"heading": "Full Text", "body": _text_versions(bill.text_versions)})
    if bill.related_bills:
        sections.append({"heading": "Related Bills", "body": _bullets(bill.related_bills)})
    if bill.sources:
        sections.append({"heading": "Sources", "body": _sources(bill.sources)})
    body = _BODY.render(sections=sections)
    region = _lawbrain_region([s for s in bill.commentary_sources if s.body])
    if region:
        # rstrip first: _BODY.render already ends with one "\n"; align the single
        # blank line before BEGIN with preserve_lawbrain_region's splice spacing
        # so a sync-written page and a refresh-spliced page are byte-identical (D20).
        body = body.rstrip("\n") + "\n\n" + region
    if bill.flipped_out:
        reason = bill.flipped_out.reason
        reason = reason.replace("-->", "--&gt;").replace('"', '\\"')
        marker = (
            f'<!-- zwiadbrain:flipped-out date="{bill.flipped_out.date.isoformat()}"'
            f' reason="{reason}" -->\n\n'
        )
        body = marker + body
    return body


def render_enforcement_body(action: EnforcementAction) -> str:
    """Render the Markdown body for an enforcement-action page (no frontmatter)."""
    sections: list[dict[str, str]] = []
    if action.summary:
        sections.append({"heading": "Summary", "body": action.summary.strip()})
    if action.developments:
        sections.append({"heading": "Developments", "body": _developments(action.developments)})
    rest: list[tuple[str, str | None]] = [
        ("Background", action.background),
        ("Allegations", action.allegations),
        ("Outcome", action.outcome),
        ("Significance", action.significance),
    ]
    for heading, value in rest:
        if value:
            sections.append({"heading": heading, "body": value.strip()})
    if action.sources:
        sections.append({"heading": "Sources", "body": _sources(action.sources)})
    body = _BODY.render(sections=sections)
    region = _lawbrain_region([s for s in action.commentary_sources if s.body])
    if region:
        # rstrip first: _BODY.render already ends with one "\n"; align the single
        # blank line before BEGIN with preserve_lawbrain_region's splice spacing
        # so a sync-written page and a refresh-spliced page are byte-identical (D20).
        body = body.rstrip("\n") + "\n\n" + region
    return body


def preserve_lawbrain_region(prev_text: str, fresh_text: str) -> str:
    """Splice a prior page's ``lawbrain:region`` block forward onto a fresh body.

    This is the body-level analog of ``preserve_leg_history`` (D63). A non-sync
    render (e.g. ``render-refreshed``) produces ``fresh_text`` WITHOUT a region,
    since the item carries commentary metadata with ``body=None``; this re-attaches
    the committed region verbatim so the data is not lost.

    - If ``fresh_text`` already contains a region, it is authoritative — returned
      unchanged (the sync path owns create/update/remove of the region).
    - Else, the begin..end block is extracted from ``prev_text`` (inclusive) and
      appended to ``fresh_text``, preserving a single trailing newline.
    - If ``prev_text`` has no region, ``fresh_text`` is returned unchanged.
    """
    if LAWBRAIN_REGION_BEGIN in fresh_text:
        return fresh_text
    begin = prev_text.find(LAWBRAIN_REGION_BEGIN)
    if begin == -1:
        return fresh_text
    end = prev_text.find(LAWBRAIN_REGION_END, begin)
    if end == -1:
        return fresh_text
    region = prev_text[begin : end + len(LAWBRAIN_REGION_END)]
    return fresh_text.rstrip("\n") + "\n\n" + region + "\n"


def render_lawbrain_region(item: Bill | EnforcementAction) -> str | None:
    """The marker-delimited law-brain region for an item's commentary, or ``None``.

    Mirrors the region appended by :func:`render_bill_body` /
    :func:`render_enforcement_body`: built only from commentary sources carrying a
    verbatim ``body`` (refresh-only bookkeeping with ``body=None`` renders nothing).
    """
    return _lawbrain_region([s for s in item.commentary_sources if s.body])


def splice_lawbrain_region(body: str, region: str | None) -> str:
    """Replace, append, or remove the ``lawbrain:region`` in a page body verbatim.

    The region is always the last body element (rendered after ``Sources``), so the
    text up to :data:`LAWBRAIN_REGION_BEGIN` is the authoritative non-commentary body
    and is preserved byte-for-byte. This lets ``/zwiad-sync-lawbrain`` own the region
    without rebuilding a bill's body-only sections (Summary / Status & Timeline /
    Full Text) from frontmatter — which would silently drop them, since they are not
    serialized (``_BODY_ONLY_FIELDS``).

    - ``region`` given       -> spliced in after the preserved body (replacing any
      existing region in place, since it sits last).
    - ``region`` is ``None`` -> the existing region (if any) is removed.
    """
    begin = body.find(LAWBRAIN_REGION_BEGIN)
    base = (body[:begin] if begin != -1 else body).rstrip("\n")
    if region:
        return base + "\n\n" + region
    return base
