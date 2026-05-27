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
    EnforcementAction,
    LegHistory,
    TextVersion,
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
    """Demote ATX headings by one level (e.g. ## -> ###) in copied commentary."""
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


def _leg_history(history: LegHistory) -> str:
    parts: list[str] = []
    if history.versions:
        parts.append("### Versions\n\n" + _text_versions(history.versions))
    if history.committee_reports:
        reports = "\n".join(
            f"- [{r.citation}]({r.url})" if r.url else f"- {r.citation}"
            for r in history.committee_reports
        )
        parts.append("### Committee Reports\n\n" + reports)
    if history.floor_consideration:
        floor = "\n".join(
            f"- {(f.date.isoformat() if f.date else '')} {(f.chamber or '')}"
            f" — {(f.congressional_record or '')}".strip()
            for f in history.floor_consideration
        )
        parts.append("### Floor Consideration\n\n" + floor)
    if history.votes:
        votes = "\n".join(
            f"- {(v.date.isoformat() if v.date else '')} {(v.chamber or '')}:"
            f" {(v.result or '')}".strip()
            for v in history.votes
        )
        parts.append("### Votes\n\n" + votes)
    if history.conference:
        parts.append("### Conference\n\n" + history.conference)
    if history.enactment:
        enactment = history.enactment
        rows = [
            f"Signed: {enactment.date_signed.isoformat()}" if enactment.date_signed else "",
            f"Public Law: {enactment.public_law}" if enactment.public_law else "",
            f"Statutes at Large: {enactment.statutes_at_large}"
            if enactment.statutes_at_large
            else "",
        ]
        parts.append("### Enactment\n\n" + "\n".join(f"- {row}" for row in rows if row))
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
    """Render the Markdown body for a bill page (no frontmatter)."""
    sections: list[dict[str, str]] = []
    if bill.summary:
        sections.append({"heading": "Summary", "body": bill.summary.strip()})
    if bill.actions:
        sections.append({"heading": "Status & Timeline", "body": _timeline(bill.actions)})
    if bill.amendments:
        sections.append({"heading": "Amendments", "body": _amendments(bill.amendments)})
    if bill.leg_history:
        sections.append({"heading": "Legislative History", "body": _leg_history(bill.leg_history)})
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
    return _BODY.render(sections=sections)


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
