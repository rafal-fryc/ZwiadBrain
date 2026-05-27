"""Frontmatter (de)serialization and validation for wiki pages.

A committed page is YAML frontmatter (metadata — the source of truth) plus a
rendered Markdown body. :func:`to_frontmatter` emits metadata only: body content
(summary prose, timeline, amendments, legislative history, and the verbatim
copied commentary text) is rendered into the body and re-derived each run, so it
is excluded here. :func:`from_page` parses a page's frontmatter back into the
correct model and surfaces validation failures as :class:`WikiSchemaError`.
"""

import frontmatter
from pydantic import ValidationError

from zwiadbrain.exceptions import WikiSchemaError
from zwiadbrain.models import Bill, EnforcementAction, parse_wiki_item

# Model fields rendered into the page body, never serialized to frontmatter.
_BODY_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "summary",
        "background",
        "allegations",
        "outcome",
        "significance",
        "actions",
        "amendments",
        "text_versions",
        "leg_history",
        "related_bills",
    }
)


def to_frontmatter(item: Bill | EnforcementAction) -> dict[str, object]:
    """Serialize a page model to its frontmatter dict (metadata only).

    Dates become ISO strings; None values and empty collections are dropped; the
    verbatim ``body`` of each commentary source is stripped (it lives in the page
    body, not the frontmatter).
    """
    raw: dict[str, object] = item.model_dump(mode="json", exclude_none=True)
    fm: dict[str, object] = {}
    for key, value in raw.items():
        if key == "commentary_sources" or key in _BODY_ONLY_FIELDS or value in ([], {}):
            continue
        fm[key] = value
    # Commentary sources are built from the typed model so the verbatim body can
    # be excluded cleanly (it is rendered into the page body, not the frontmatter).
    if item.commentary_sources:
        fm["commentary_sources"] = [
            source.model_dump(mode="json", exclude_none=True, exclude={"body"})
            for source in item.commentary_sources
        ]
    return fm


def from_page(text: str) -> Bill | EnforcementAction:
    """Parse a page's frontmatter into the correct model, validating required fields."""
    metadata: dict[str, object] = frontmatter.loads(text).metadata
    try:
        return parse_wiki_item(metadata)
    except ValidationError as exc:
        raise WikiSchemaError(str(exc)) from exc
