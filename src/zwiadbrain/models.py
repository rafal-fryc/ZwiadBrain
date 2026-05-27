"""ZwiadBrain domain models.

These pydantic models are the typed shape of the committed wiki frontmatter,
which is the project's source of truth. Two concrete page kinds — :class:`Bill`
and :class:`EnforcementAction` — share the :class:`WikiItem` base and form a
discriminated union keyed on ``type``; :func:`parse_wiki_item` routes a
frontmatter dict to the correct one.

``datetime`` is imported module-qualified (``dt``) on purpose: several models
have a field named ``date``, which would otherwise shadow the ``date`` type when
its annotation is evaluated.
"""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class CommentarySource(BaseModel):
    """A law-brain page whose content has been copied onto a tracked page.

    Carries the bookkeeping that lets Pass A detect when copied commentary is
    stale and re-copy it (``content_hash``), plus how the link was established.
    """

    path: str
    slug: str
    updated: dt.date | None = None
    content_hash: str
    matched_by: Literal["deterministic", "llm"]
    confidence: float


class Action(BaseModel):
    """A single deterministic action in a bill's status timeline."""

    date: dt.date | None = None
    chamber: str | None = None
    text: str
    action_type: str | None = None


class Amendment(BaseModel):
    """An amendment to a bill, with a plain-language explanation of its effect."""

    number: str
    sponsor: str | None = None
    chamber: str | None = None
    status: str | None = None
    what_changed: str | None = None


class TextVersion(BaseModel):
    """A published text version of a bill (e.g. Introduced, Engrossed, Enrolled)."""

    code: str
    date: dt.date | None = None
    url: str | None = None


class CommitteeReport(BaseModel):
    """A committee report citation in a bill's legislative history."""

    citation: str
    url: str | None = None


class FloorAction(BaseModel):
    """Floor consideration with a Congressional Record citation."""

    date: dt.date | None = None
    chamber: str | None = None
    congressional_record: str | None = None
    url: str | None = None


class Vote(BaseModel):
    """A recorded vote in a bill's legislative history."""

    date: dt.date | None = None
    chamber: str | None = None
    result: str | None = None
    roll_call_url: str | None = None


class Enactment(BaseModel):
    """Enactment details recorded when a bill becomes law."""

    date_signed: dt.date | None = None
    public_law: str | None = None
    statutes_at_large: str | None = None


class LegHistory(BaseModel):
    """Standardized legislative history, assembled once a bill is enacted."""

    versions: list[TextVersion] = []
    committee_reports: list[CommitteeReport] = []
    floor_consideration: list[FloorAction] = []
    votes: list[Vote] = []
    conference: str | None = None
    enactment: Enactment | None = None


class WikiItem(BaseModel):
    """Fields shared by every committed wiki page."""

    id: str
    jurisdiction: str
    title: str
    topics: list[str] = []
    sources: dict[str, str] = {}
    commentary_sources: list[CommentarySource] = []
    tracking: bool = True
    last_synced: dt.datetime | None = None


class Bill(WikiItem):
    """A tracked piece of legislation (federal or state)."""

    type: Literal["bill"] = "bill"
    bill_number: str
    chamber: str | None = None
    congress: str | None = None
    session: str | None = None
    status: str | None = None
    policy_area: str | None = None
    sponsors: list[str] = []
    introduced_date: dt.date | None = None
    latest_action_date: dt.date | None = None
    latest_action: str | None = None
    enacted: bool = False
    public_law: str | None = None
    actions: list[Action] = []
    amendments: list[Amendment] = []
    text_versions: list[TextVersion] = []
    leg_history: LegHistory | None = None
    related_bills: list[str] = []
    change_hash: str | None = None
    update_date: str | None = None


class EnforcementAction(WikiItem):
    """A tracked enforcement action (FTC or state Attorney General)."""

    type: Literal["enforcement"] = "enforcement"
    agency: str
    respondent: str | None = None
    action_type: str | None = None
    statutes: list[str] = []
    date_filed: dt.date | None = None
    date_resolved: dt.date | None = None
    penalties: str | None = None
    status: str | None = None
    docket: str | None = None


WikiItemUnion = Annotated[Bill | EnforcementAction, Field(discriminator="type")]
_ADAPTER: TypeAdapter[Bill | EnforcementAction] = TypeAdapter(WikiItemUnion)


def parse_wiki_item(data: dict[str, object]) -> Bill | EnforcementAction:
    """Parse a frontmatter dict into the correct concrete page model by ``type``."""
    return _ADAPTER.validate_python(data)
