"""Markdown page-body builders for bill and enforcement wiki pages.

A single jinja2 template renders a pre-built, already-filtered list of
``{heading, body}`` sections, so output is deterministic. Section content
(timeline, amendments, legislative history, copied commentary) is assembled by
the typed helpers below; empty sections are dropped by the callers.
"""

import re

import jinja2

from zwiadbrain.models import (
    Action,
    Amendment,
    Bill,
    CommentarySource,
    Enactment,
    EnforcementAction,
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


def _demote_headings(text: str) -> str:
    """Demote ATX headings by one level (## -> ###) in copied commentary.

    Markdown has no h7, so the demotion is clamped at h6: an h1-h5 heading gains
    one ``#``, and an h6 heading is left at h6 (the ``{1,5}`` bound never matches
    a 6-hash run, so it cannot produce a 7-hash heading).
    """
    return re.sub(r"(?m)^(#{1,5})(?= )", r"#\1", text)


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
    body = _demote_headings(source.body.strip()) if source.body else ""
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
    if bill.commentary_sources:
        sections.append(
            {"heading": "Commentary & Analysis", "body": _commentary(bill.commentary_sources)}
        )
    if bill.sources:
        sections.append({"heading": "Sources", "body": _sources(bill.sources)})
    body = _BODY.render(sections=sections)
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
    prose: list[tuple[str, str | None]] = [
        ("Summary", action.summary),
        ("Background", action.background),
        ("Allegations", action.allegations),
        ("Outcome", action.outcome),
        ("Significance", action.significance),
    ]
    for heading, value in prose:
        if value:
            sections.append({"heading": heading, "body": value.strip()})
    if action.commentary_sources:
        sections.append(
            {"heading": "Commentary & Analysis", "body": _commentary(action.commentary_sources)}
        )
    if action.sources:
        sections.append({"heading": "Sources", "body": _sources(action.sources)})
    return _BODY.render(sections=sections)
