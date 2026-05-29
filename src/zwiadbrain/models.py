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

from pydantic import AfterValidator, BaseModel, Field, TypeAdapter, model_validator

from zwiadbrain.exceptions import ConfigError


def _require_http(value: str) -> str:
    """Assert a URL string starts with ``http://`` or ``https://``.

    Returns the value UNCHANGED on success so the serialized bytes are
    byte-identical (D20) — unlike pydantic's ``HttpUrl``, which reformats.
    """
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(f"url must start with http:// or https://, got: {value!r}")
    return value


_HttpUrlStr = Annotated[str, AfterValidator(_require_http)]


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
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    body: str | None = None  # verbatim copied page body; rendered, not stored in frontmatter


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
    latest_action_date: dt.date | None = None
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


class Hearing(BaseModel):
    """A congressional hearing relevant to a bill's legislative history."""

    title: str
    committee: str | None = None
    chamber: str | None = None
    date: dt.date | None = None
    citation: str | None = None
    url: str | None = None


class Statement(BaseModel):
    """A recorded statement by a legislator, witness, or other participant."""

    speaker: str
    role: Literal["sponsor", "cosponsor", "member", "witness", "other"]
    date: dt.date | None = None
    quote: Annotated[str, Field(min_length=20)]  # D36 grounding floor (_MIN_QUOTE_CHARS)
    context: str | None = None
    source_url: _HttpUrlStr
    source_type: Literal["CREC", "hearing", "press", "news", "other"]
    verified: bool = False


class StatutesAtLarge(BaseModel):
    """Statutes-at-Large citation for an enacted public law.

    Carries the canonical citation (e.g. ``"138 Stat. 1234"``) and a clickable
    GovInfo ``app/details`` URL.  ``url`` is required: the project's leg-history
    rule is "no link, no render" (matching ``Hearing``, ``CommitteeReport``, etc.).
    """

    citation: Annotated[str, Field(min_length=1)]
    url: _HttpUrlStr


class Enactment(BaseModel):
    """Enactment details recorded when a bill becomes law."""

    date_signed: dt.date | None = None
    public_law: str | None = None
    statutes_at_large: StatutesAtLarge | None = None
    url: str | None = None


class LegHistory(BaseModel):
    """Standardized legislative history, assembled once a bill is enacted."""

    versions: list[TextVersion] = []
    committee_reports: list[CommitteeReport] = []
    floor_consideration: list[FloorAction] = []
    votes: list[Vote] = []
    conference: str | None = None
    enactment: Enactment | None = None
    hearings: list[Hearing] = []
    statements: list[Statement] = []
    narrative: str | None = None


class FlipOutAudit(BaseModel):
    """Audit record for a bill whose classifier verdict flipped IN→OUT during refresh.

    Persisted to frontmatter so a future ``reindex`` re-reads it; the renderer
    emits an ``<!-- zwiadbrain:flipped-out … -->`` comment in the body from it.
    Survives a fresh clone via committed wiki history.
    """

    date: dt.date
    reason: Annotated[str, Field(min_length=1)]


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
    summary: str | None = None  # plain-language summary prose (body content)


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
    # LegiScan internal bill_id (state bills only; None for federal). The stable native
    # cursor key used by refresh to match a page against a getMasterListRaw entry — the
    # wiki id does not contain it (D48).
    legiscan_bill_id: int | None = None
    # str (not dt.date): a full ISO timestamp cursor (Congress.gov updateDate)
    # compared by raw equality in refresh.detect_refreshable, never date math —
    # retyping would drop the time component and reformat the bytes (D20).
    update_date: str | None = None
    update_date_text: str | None = None
    summary_hash: str | None = None
    amendments_count: int = 0
    flipped_out: FlipOutAudit | None = None

    @model_validator(mode="after")
    def _check_federal_id_shape(self) -> "Bill":
        """Federal (``jurisdiction == "US"``) ids must be ``<congress>-<type>-<number>``.

        Parsed via the shared :func:`parse_bill_id`, which raises ``ConfigError``
        on a malformed id; re-raised here as ``ValueError`` so pydantic surfaces
        it as a ``ValidationError``.  State ids (e.g. ``us-ca-sb-362``) use a
        different shape and are left unchecked.  This only validates — it never
        rewrites ``self.id`` — so serialized output is byte-identical (D20).
        """
        if self.jurisdiction == "US":
            from zwiadbrain.pipeline.ids import parse_bill_id  # noqa: PLC0415

            try:
                parse_bill_id(self.id)
            except ConfigError as exc:
                raise ValueError(str(exc)) from exc
        return self


class EnforcementDevelopment(BaseModel):
    """A single development in an enforcement matter (complaint, order, settlement).

    Matters accrue developments over time as agencies publish new feed items about
    the same case. Persisted to frontmatter (it cannot be re-derived) AND rendered
    into the page body — the same treatment leg_history research gets (D40).
    """

    date: dt.date | None = None  # None when the source carries no explicit date
    summary: Annotated[str, Field(min_length=1)]
    source_url: _HttpUrlStr


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
    # Body-content prose sections (rendered, not stored in frontmatter):
    background: str | None = None
    allegations: str | None = None
    outcome: str | None = None
    significance: str | None = None
    # Append-only list of feed-item developments; persisted to frontmatter (source of
    # truth) and rendered as the "Developments" timeline section (D52).
    developments: list[EnforcementDevelopment] = []


WikiItemUnion = Annotated[Bill | EnforcementAction, Field(discriminator="type")]
_ADAPTER: TypeAdapter[Bill | EnforcementAction] = TypeAdapter(WikiItemUnion)


def parse_wiki_item(data: dict[str, object]) -> Bill | EnforcementAction:
    """Parse a frontmatter dict into the correct concrete page model by ``type``."""
    return _ADAPTER.validate_python(data)
