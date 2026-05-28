"""Frontmatter (de)serialization and validation for wiki pages.

A committed page is YAML frontmatter (metadata — the source of truth) plus a
rendered Markdown body. :func:`to_frontmatter` emits metadata only: body content
(summary prose, timeline, amendments, and the verbatim copied commentary text)
is rendered into the body and re-derived each run, so it is excluded here.

**leg_history partial persistence:** ``leg_history.hearings``,
``leg_history.statements``, and ``leg_history.narrative`` are expensive,
non-deterministic outputs and persist to frontmatter (D40 extends D37 to add
narrative).  The deterministic spine fields (``versions``,
``committee_reports``, ``floor_consideration``, ``votes``, ``conference``,
``enactment``) remain body-only and are re-derived from the API on each
render.

:func:`from_page` parses a page's frontmatter back into the correct model and
surfaces validation failures as :class:`WikiSchemaError`.
"""

import frontmatter
import yaml
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
        if key == "amendments_count" and value == 0:
            continue
        fm[key] = value
    # Commentary sources are built from the typed model so the verbatim body can
    # be excluded cleanly (it is rendered into the page body, not the frontmatter).
    if item.commentary_sources:
        fm["commentary_sources"] = [
            source.model_dump(mode="json", exclude_none=True, exclude={"body"})
            for source in item.commentary_sources
        ]
    # Persist the researched leg_history sub-fields plus the narrative (D40).
    # The deterministic spine (versions, committee_reports, floor_consideration,
    # votes, conference, enactment) remains body-only / re-derived per D37.
    if isinstance(item, Bill) and item.leg_history is not None:
        lh_fm: dict[str, object] = {}
        if item.leg_history.hearings:
            lh_fm["hearings"] = [
                h.model_dump(mode="json", exclude_none=True)
                for h in item.leg_history.hearings
            ]
        if item.leg_history.statements:
            lh_fm["statements"] = [
                s.model_dump(mode="json", exclude_none=True)
                for s in item.leg_history.statements
            ]
        if item.leg_history.narrative:
            lh_fm["narrative"] = item.leg_history.narrative
        if lh_fm:
            fm["leg_history"] = lh_fm
    return fm


def from_page(text: str) -> Bill | EnforcementAction:
    """Parse a page's frontmatter into the correct model, validating required fields."""
    try:
        metadata: dict[str, object] = frontmatter.loads(text).metadata
        return parse_wiki_item(metadata)
    except yaml.YAMLError as exc:
        raise WikiSchemaError(f"malformed frontmatter YAML: {exc}") from exc
    except ValidationError as exc:
        raise WikiSchemaError(str(exc)) from exc
