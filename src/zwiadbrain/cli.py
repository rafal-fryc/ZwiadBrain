"""ZwiadBrain command-line interface.

These are the deterministic fetch/render halves that the interactive Claude Code
slash commands drive (the subagents run between a fetch and a render; Python
makes no LLM calls — DECISIONS.md D26/D27). Commands:

- ``version`` / ``reindex`` — utilities.
- ``backfill`` — deterministic discover→enrich→render (no classification).
- ``fetch-candidates`` / ``render-classified`` — the ``/zwiad-backfill`` halves.
- ``fetch-leg-history`` / ``render-leg-history`` — the ``/zwiad-leg-history`` halves.
- ``fetch-refreshable`` / ``render-refreshed`` — the ``/zwiad-refresh`` halves.
- ``fetch-state-candidates`` / ``fetch-state-refreshable`` — ``/zwiad-scan-states``.
- ``fetch-enforcement-candidates`` / ``render-enforcement`` — ``/zwiad-scan-enforcement``.
- ``fetch-lawbrain-candidates`` / ``render-lawbrain-commentary`` — ``/zwiad-sync-lawbrain``.

See ``ARCHITECTURE.md`` for the full command list and the slash commands they back.
"""

import contextlib
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal

import httpx
import typer
from pydantic import ValidationError

from zwiadbrain import __version__
from zwiadbrain.config import Settings, load_settings
from zwiadbrain.exceptions import AppError, ConfigError, WikiSchemaError
from zwiadbrain.models import (
    Bill,
    EnforcementAction,
    EnforcementDevelopment,
    Hearing,
    LegHistory,
    Statement,
)
from zwiadbrain.pipeline.discover import keyword_filter, recall_filter
from zwiadbrain.pipeline.enforcement import (
    MatterRef,
    confirm_match,
    merge_current_state,
    merge_developments,
)
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.pipeline.ids import build_enforcement_id, parse_bill_id, parse_strong_key
from zwiadbrain.pipeline.lawbrain_copy import (
    build_commentary_source,
    detect_stale,
    merge_commentary,
)
from zwiadbrain.pipeline.lawbrain_keys import keys_hash, page_keys, tracked_item_keys
from zwiadbrain.pipeline.lawbrain_links import harvest_links
from zwiadbrain.pipeline.lawbrain_match import TargetRef, build_shortlist
from zwiadbrain.pipeline.lawbrain_match import confirm_match as lawbrain_confirm_match
from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry
from zwiadbrain.pipeline.lawbrain_review import (
    ReviewEntry,
    parse_review_queue,
    render_review_queue,
)
from zwiadbrain.pipeline.leg_history import assemble_spine, collect_leads, ground_items
from zwiadbrain.pipeline.refresh import (
    apply_classifier_flip,
    clear_flip,
    detect_refreshable,
    detect_state_refreshable,
    preserve_leg_history,
    summary_hash,
)
from zwiadbrain.pipeline.render import write_lawbrain_region, write_page
from zwiadbrain.pipeline.run_log import RunSummary, append_run_log, format_run_log_entry
from zwiadbrain.pipeline.staging import stage_json, validate_model
from zwiadbrain.reference.loader import load_reference
from zwiadbrain.sources.base import Candidate
from zwiadbrain.sources.congress import CongressSource
from zwiadbrain.sources.enforcement.base import EnforcementSource
from zwiadbrain.sources.enforcement.ftc import FTCSource
from zwiadbrain.sources.enforcement.state_ag import StateAGSource
from zwiadbrain.sources.govinfo import GovInfoSource
from zwiadbrain.sources.lawbrain import LawBrainPage, LawBrainReader
from zwiadbrain.sources.legiscan import LegiScanSource
from zwiadbrain.store import Store
from zwiadbrain.wiki.schema import from_page

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TOPICS = Path("reference/topics.yaml")
_SCAN_LIMIT = 250  # bills to scan per fetch-candidates run (Congress list single-request max)
_MAX_PROBE = 250  # max Stage-2 policyArea probes per run (PHASE-03.1)

app = typer.Typer(
    name="zwiadbrain",
    help="Track U.S. AI/privacy/cyber legislation and enforcement actions.",
    no_args_is_help=True,
)


@app.callback()
def root() -> None:
    """ZwiadBrain command-line interface.

    A callback is present so the app stays a multi-command group (each command
    keeps its own name rather than collapsing into a single-command program).
    """


@app.command()
def version() -> None:
    """Print the installed ZwiadBrain version."""
    typer.echo(__version__)


@app.command()
def reindex(
    wiki: Annotated[Path, typer.Option(help="Wiki root to index.")] = Path("wiki"),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path("data/cache/index.sqlite"),
) -> None:
    """Rebuild the SQLite index/watchlist from committed wiki frontmatter."""
    try:
        with Store(db) as store:
            count = store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"reindexed {count} pages from {wiki}")


@app.command()
def backfill(
    congress: Annotated[int, typer.Option(min=1, help="Congress number, e.g. 118.")],
    limit: Annotated[int, typer.Option(min=1, help="Max bills to enrich and render.")] = 5,
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    seed: Annotated[
        list[str] | None, typer.Option(help="Keyword seed for recall filtering (repeatable).")
    ] = None,
    force: Annotated[
        str | None,
        typer.Option(
            help="Re-fetch+enrich a single flipped-out bill (congress/type/number) and re-track it."
        ),
    ] = None,
) -> None:
    """Enrich and render federal bills from a Congress into the wiki.

    With ``--force <congress/type/number>`` the discover path is skipped: the one
    named bill is re-fetched, re-enriched, and written re-tracked (``tracking=true``,
    flip audit cleared) so a previously flipped-out bill can come back (F7). The
    in/out-of-scope verdict is the slash command's classifier step (D26).
    """
    try:
        api_key = load_settings().require_congress_api_key()
        source = CongressSource(api_key)
        if force is not None:
            parse_bill_id(force.replace("/", "-"))  # validate shape early (raises ConfigError)
            fresh = clear_flip(
                enrich(
                    source,
                    Candidate(source=source.name, native_id=force, jurisdiction="US", title=""),
                )
            )
            written = write_page(fresh, wiki)
            typer.echo(f"re-tracked {written} bill into {wiki}")
            return
        candidates = source.discover(congress=congress, limit=limit * 5 if seed else limit)
        candidates = keyword_filter(candidates, seed)[:limit]
        written = sum(write_page(enrich(source, candidate), wiki) for candidate in candidates)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"backfilled {written} federal bill(s) into {wiki}")


@app.command(name="fetch-candidates")
def fetch_candidates(
    congress: Annotated[int, typer.Option(min=1, help="Congress number, e.g. 118.")],
    limit: Annotated[int, typer.Option(min=1, help="Max candidates to fetch.")] = 5,
    seed: Annotated[
        list[str] | None,
        typer.Option(help="Keyword seed (repeatable); defaults to topics.yaml seeds."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option(help="Run directory for candidates.json.")
    ] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Fetch keyword-matched federal candidates and stage them for classification.

    The deterministic first half of the LLM pipeline: discover -> keyword recall
    filter -> enrich, writing fully-fetched ``Bill``s to ``candidates.json`` for
    the interactive session's classifier/summarizer subagents to consume.
    """
    try:
        # Explicit --seed is a targeted search (no taxonomy load, no Stage-2 probe);
        # default discovery uses topics.yaml seeds + the broad policyArea allowlist.
        if seed:
            seeds, policy_areas = seed, []
        else:
            reference = load_reference(topics)
            seeds, policy_areas = reference.seeds, reference.policy_areas
        api_key = load_settings().require_congress_api_key()
        source = CongressSource(api_key)
        scanned = source.discover(congress=congress, limit=_SCAN_LIMIT)
        candidates = recall_filter(
            scanned,
            source,
            seeds=seeds,
            policy_areas=policy_areas,
            limit=limit,
            max_probe=_MAX_PROBE,
        )
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} candidate(s) to {path}")


@app.command(name="render-classified")
def render_classified(
    input_file: Annotated[Path, typer.Option("--in", help="classified.json to render.")],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Render classified, in-scope bills into the wiki, validating their topics.

    The deterministic second half: the interactive session hands back in-scope
    ``Bill``s (topics/summary/what_changed applied by subagents); this validates
    ``topics`` against the taxonomy and renders the pages.
    """
    try:
        topic_keys = set(load_reference(topics).topic_keys)
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read classified file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(
                f"classified file must be a JSON list, got {type(raw).__name__}"
            )
        items: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        bills: list[Bill] = []
        for item in items:
            bills.append(validate_model(Bill, item, label="classified bill"))
        for bill in bills:
            unknown = [topic for topic in bill.topics if topic not in topic_keys]
            if unknown:
                raise ConfigError(f"bill {bill.id} has unknown topic(s): {', '.join(unknown)}")
        written = sum(write_page(bill, wiki) for bill in bills)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"rendered {written} page(s) into {wiki}")


@app.command(name="fetch-state-candidates")
def fetch_state_candidates(
    state: Annotated[str, typer.Option(help="Two-letter state, e.g. ca.")],
    limit: Annotated[int, typer.Option(min=1, help="Max candidates to fetch.")] = 5,
    query: Annotated[
        str | None,
        typer.Option(help="LegiScan full-text query; defaults to topics.yaml seeds."),
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Search a state via LegiScan and stage enriched candidate bills for classification.

    The deterministic first half of ``/zwiad-scan-states``: getSearchRaw recall →
    getBill enrich → ``candidates.json`` for the interactive classifier/summarizer
    subagents. The search query is the recall stage (D50), so no title pre-filter runs.
    """
    try:
        if query:
            search_query = query
        else:
            seeds = load_reference(topics).seeds
            # Quote multi-word seeds as exact phrases; OR-join (D50 §8).
            terms = [f'"{s}"' if " " in s else s for s in seeds]
            search_query = " OR ".join(terms)
        api_key = load_settings().require_legiscan_api_key()
        source = LegiScanSource(api_key, state, query=search_query)
        candidates = source.discover(limit=limit)
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} {state} candidate(s) to {path}")


@app.command(name="fetch-state-refreshable")
def fetch_state_refreshable(
    wiki: Annotated[Path, typer.Option(help="Wiki root to scan for tracked state bills.")] = Path(
        "wiki"
    ),
    out: Annotated[Path | None, typer.Option(help="Run directory for refreshable.json.")] = None,
) -> None:
    """Detect tracked state bills whose LegiScan change_hash advanced (incremental sync).

    One getMasterListRaw per state returns every current-session bill's change_hash;
    only bills whose stored hash differs are re-fetched via getBill. The staged entries
    share the shape `/zwiad-refresh` consumes, so render-refreshed is reused unchanged.
    """
    try:
        api_key = load_settings().require_legiscan_api_key()
        states_dir = wiki / "states"
        if not states_dir.exists():
            typer.echo(f"no states directory under {wiki}", err=True)
            raise typer.Exit(0)
        # Group tracked state bills by state code.
        by_state: dict[str, list[Bill]] = {}
        skipped = 0
        for page_path in sorted(states_dir.glob("*/bills/*.md")):
            try:
                item = from_page(page_path.read_text(encoding="utf-8"))
            except (WikiSchemaError, ConfigError) as exc:
                skipped += 1
                typer.echo(f"skipped {page_path}: {exc}", err=True)
                continue
            if not isinstance(item, Bill) or not item.tracking or item.legiscan_bill_id is None:
                continue
            state = item.jurisdiction.split("-", 1)[-1].lower()
            by_state.setdefault(state, []).append(item)
        entries: list[dict[str, object]] = []
        for state, bills in sorted(by_state.items()):
            source = LegiScanSource(api_key, state)
            hashes = source.change_hashes()
            for prev in bills:
                fresh_hash = hashes.get(prev.legiscan_bill_id or -1)
                if fresh_hash is None or fresh_hash == prev.change_hash:
                    continue  # absent from current session, or unchanged → no getBill
                fresh = source.fetch(str(prev.legiscan_bill_id))
                fresh.summary_hash = summary_hash(fresh.summary)
                fresh.amendments_count = len(fresh.amendments)
                refreshable = detect_state_refreshable(prev, fresh)
                if refreshable is None:
                    continue
                entries.append({
                    "bill_id": prev.id,
                    "prev": prev.model_dump(mode="json"),
                    "fresh": fresh.model_dump(mode="json"),
                    "needs_classifier": refreshable.needs_classifier,
                    "needs_summarizer": refreshable.needs_summarizer,
                    "changed_amendment_numbers": list(refreshable.changed_amendment_numbers),
                })
        path = stage_json(entries, name="refreshable.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(entries)} refreshable state bill(s) to {path} ({skipped} skipped)")


@app.command(name="fetch-leg-history")
def fetch_leg_history(
    bill: Annotated[
        str, typer.Option(help="Bill in congress/type/number form, e.g. 118/hr/9020.")
    ],
    out: Annotated[
        Path | None, typer.Option(help="Run directory for leghistory.json.")
    ] = None,
) -> None:
    """Fetch an enacted federal bill and stage its legislative-history inputs.

    Assembles the deterministic spine (text versions, committee reports, votes,
    floor consideration, enactment) and research leads (hearing candidates) via
    Congress.gov and GovInfo, writing them to ``leghistory.json`` for the
    interactive session's researcher/verifier subagents to consume.
    """
    try:
        # Validate the --bill shape before any network call: slash form
        # (118/hr/9020) maps to the dashed id parse_bill_id consumes; a malformed
        # arg raises ConfigError here rather than producing a confusing fetch error.
        parse_bill_id(bill.replace("/", "-"))
        settings = load_settings()
        congress_source = CongressSource(settings.require_congress_api_key())
        fetched = congress_source.fetch(bill)
        if not fetched.enacted:
            raise ConfigError(
                f"bill {fetched.id} is not enacted — legislative history is assembled"
                " only for enacted bills"
            )
        govinfo_source = GovInfoSource(settings.require_govinfo_api_key())
        spine = assemble_spine(fetched, congress_source, govinfo_source)
        leads = collect_leads(fetched, govinfo_source)
        payload = {
            "bill": fetched.model_dump(mode="json"),
            "spine": spine.model_dump(mode="json"),
            "leads": leads,
        }
        path = stage_json(payload, name="leghistory.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged legislative-history inputs for {fetched.id} to {path}")


@app.command(name="fetch-refreshable")
def fetch_refreshable(
    wiki: Annotated[Path, typer.Option(help="Wiki root to scan for tracked bills.")] = Path("wiki"),
    out: Annotated[
        Path | None, typer.Option(help="Run directory for refreshable.json.")
    ] = None,
) -> None:
    """Detect tracked federal bills whose Congress.gov cursors have advanced.

    Reads every ``wiki/federal/bills/*.md`` page, re-fetches each tracked bill
    via Congress.gov, compares update-date cursors, and stages the changed
    bills + their subagent triggers to ``refreshable.json`` for the
    ``/zwiad-refresh`` slash command.
    """
    try:
        settings = load_settings()
        congress_source = CongressSource(settings.require_congress_api_key())
        govinfo_source = GovInfoSource(settings.require_govinfo_api_key())
        bills_dir = wiki / "federal" / "bills"
        if not bills_dir.exists():
            typer.echo(f"no federal bills directory under {wiki}", err=True)
            raise typer.Exit(0)
        entries: list[dict[str, object]] = []
        skipped = 0
        for page_path in sorted(bills_dir.glob("*.md")):
            try:
                text = page_path.read_text(encoding="utf-8")
                item = from_page(text)
                if not isinstance(item, Bill) or not item.tracking:
                    continue
                congress, bill_type, number = parse_bill_id(item.id)
                native_id = f"{congress}/{bill_type}/{number}"
                fresh = congress_source.fetch(native_id)
                # Cross-source enrich seam: compute the cursors that source.fetch
                # cannot (they straddle the source/pipeline boundary by design).
                fresh.summary_hash = summary_hash(fresh.summary)
                fresh.amendments_count = len(fresh.amendments)
                # For enacted bills, also re-derive the leg-history spine so
                # render-refreshed can reattach prev's hearings/statements/narrative.
                if fresh.enacted:
                    fresh.leg_history = assemble_spine(fresh, congress_source, govinfo_source)
                refreshable = detect_refreshable(item, fresh)
                if refreshable is None:
                    continue
                entries.append({
                    "bill_id": item.id,
                    "prev": item.model_dump(mode="json"),
                    "fresh": fresh.model_dump(mode="json"),
                    "needs_classifier": refreshable.needs_classifier,
                    "needs_summarizer": refreshable.needs_summarizer,
                    "changed_amendment_numbers": list(refreshable.changed_amendment_numbers),
                })
            except (WikiSchemaError, ConfigError) as exc:
                skipped += 1
                typer.echo(f"skipped {page_path}: {exc}", err=True)
                continue
        path = stage_json(entries, name="refreshable.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(entries)} refreshable bill(s) to {path} ({skipped} skipped)")


@app.command(name="render-refreshed")
def render_refreshed(
    input_file: Annotated[
        Path, typer.Option("--in", help="refreshed.json staged by /zwiad-refresh."),
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path("data/cache/index.sqlite"),
) -> None:
    """Apply subagent outputs, the D38 preservation rule, and the IN→OUT flip; render + reindex."""
    try:
        raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ConfigError(
                f"refreshed.json must be a JSON list, got {type(raw).__name__}"
            )
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        refreshed_count = 0
        flipped_out: list[tuple[str, str]] = []
        for item in entries:
            if not isinstance(item, dict):
                raise ConfigError("each entry in refreshed.json must be a JSON object")
            entry: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
            if "prev" not in entry:
                raise ConfigError("refreshed.json entry is missing required key 'prev'")
            if "bill" not in entry:
                raise ConfigError("refreshed.json entry is missing required key 'bill'")
            prev = validate_model(Bill, entry["prev"], label="prev")
            bill = validate_model(Bill, entry["bill"], label="bill")
            in_scope = bool(entry.get("classifier_in_scope", True))
            rationale = str(entry.get("classifier_rationale") or "")
            # Preserve leg-history research onto fresh spine.
            if prev.leg_history is not None and bill.leg_history is not None:
                bill = bill.model_copy(update={
                    "leg_history": preserve_leg_history(prev.leg_history, bill.leg_history),
                })
            elif prev.leg_history is not None and bill.leg_history is None:
                # Defensive: a fresh non-enacted bill has no spine, but prev had research.
                # Carry prev.leg_history through unchanged so the research is not lost.
                bill = bill.model_copy(update={"leg_history": prev.leg_history})
            # Preserve law-brain commentary bookkeeping (D63). The freshly-fetched bill
            # never touches the law brain, so its commentary_sources is empty; carry
            # prev's onto it so the frontmatter survives. The verbatim lawbrain:region
            # body block is preserved separately by write_page.
            if prev.commentary_sources:
                bill = bill.model_copy(
                    update={"commentary_sources": prev.commentary_sources}
                )
            # Apply classifier verdict (no-op when in_scope=True, flip when False).
            bill = apply_classifier_flip(
                bill,
                in_scope=in_scope,
                rationale=rationale,
                date=dt.datetime.now(dt.UTC).date(),
            )
            # Re-stamp the refresh cursors from the merged bill rather than trusting the
            # subagent to echo them; otherwise the next fetch-refreshable falsely flags
            # text_changed (F1).
            bill = bill.model_copy(update={
                "summary_hash": summary_hash(bill.summary),
                "amendments_count": len(bill.amendments),
            })
            write_page(bill, wiki)
            refreshed_count += 1
            if not bill.tracking and bill.flipped_out is not None:
                flipped_out.append((bill.id, bill.flipped_out.reason))
        # Reindex after all writes.
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    flipped_count = len(flipped_out)
    typer.echo(
        f"refresh complete: refreshed {refreshed_count} / {flipped_count} flipped-out"
    )
    for bill_id, reason in flipped_out:
        typer.echo(f"  flipped-out: {bill_id} — \"{reason}\"")


def _enforcement_sources(settings: Settings, agency: str | None) -> list[EnforcementSource]:
    """Build the enabled enforcement sources, optionally filtered to one --agency."""
    sources: list[EnforcementSource] = []
    enf = settings.enforcement
    if enf.ftc.enabled and agency in (None, "ftc"):
        sources.append(FTCSource(enf.ftc.rss_url))
    for ag in enf.enabled_state_ags():
        if agency in (None, ag.agency_slug):
            sources.append(
                StateAGSource(
                    name=ag.name,
                    agency_slug=ag.agency_slug,
                    jurisdiction=ag.jurisdiction,
                    url=ag.url,
                    kind=ag.kind,
                    item_selector=ag.item_selector,
                )
            )
    return sources


def _jurisdiction_slug_map(settings: Settings) -> dict[str, str]:
    """Map a page jurisdiction -> agency_slug from config (one source per jurisdiction)."""
    mapping = {"US": "ftc"}
    for ag in settings.enforcement.state_ag:
        mapping[ag.jurisdiction] = ag.agency_slug
    return mapping


def _existing_matters(wiki: Path, settings: Settings) -> list[MatterRef]:
    """Read every tracked enforcement page into a MatterRef (for matching/shortlists)."""
    juris_slug = _jurisdiction_slug_map(settings)
    matters: list[MatterRef] = []
    for page in sorted(wiki.glob("**/enforcement/*.md")):
        try:
            item = from_page(page.read_text(encoding="utf-8"))
        except (WikiSchemaError, ConfigError):
            continue
        if not isinstance(item, EnforcementAction):
            continue
        matters.append(
            MatterRef(
                id=item.id,
                agency_slug=juris_slug.get(item.jurisdiction, ""),
                jurisdiction=item.jurisdiction,
                respondent=item.respondent,
                date_filed=item.date_filed,
                strong_key=item.docket,
            )
        )
    return matters


@app.command(name="fetch-enforcement-candidates")
def fetch_enforcement_candidates(
    agency: Annotated[
        str | None, typer.Option(help="One source: 'ftc' or an AG slug; omit for all.")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, help="Max items per source.")] = 5,
    lookback_days: Annotated[
        int | None, typer.Option(help="Override config lookback window.")
    ] = None,
    wiki: Annotated[Path, typer.Option(help="Wiki root (for existing matters).")] = Path("wiki"),
    out: Annotated[
        Path | None, typer.Option(help="Run directory for candidates.json.")
    ] = None,
) -> None:
    """Discover enforcement items (forward-from-now), fetch article text, parse strong
    keys, and stage candidates.json + matters.json for the interactive subagents."""
    try:
        settings = load_settings()
        window = (
            lookback_days
            if lookback_days is not None
            else settings.enforcement.lookback_days
        )
        since = dt.datetime.now(dt.UTC) - dt.timedelta(days=window)
        sources = _enforcement_sources(settings, agency)
        matters = _existing_matters(wiki, settings) if wiki.exists() else []
        by_key = {m.strong_key: m.id for m in matters if m.strong_key}
        candidates: list[dict[str, object]] = []
        for source in sources:
            for cand in source.discover(since=since, limit=limit):
                # Isolate per-article failures: a single moved/4xx press-release URL
                # must not abort the whole run (D54 isolation, at the article level).
                # FTC raises SourceFetchError (AppError); StateAG raises
                # httpx.HTTPStatusError (NOT an AppError) — catch both, skip, continue.
                try:
                    text = source.fetch_text(cand)
                except (AppError, httpx.HTTPError) as exc:
                    _LOGGER.warning("fetch_text failed for %s: %s", cand.url, exc)
                    continue
                strong_key = parse_strong_key(f"{cand.title}\n{text}")
                matter_id = by_key.get(strong_key) if strong_key else None
                entry: dict[str, object] = dict(cand.model_dump(mode="json"))
                entry["text"] = text
                entry["strong_key"] = strong_key
                entry["matter_id"] = matter_id
                entry["match_source"] = "strong_key" if matter_id else None
                candidates.append(entry)
        # Stage both files in the SAME run directory: stage_json writes <out>/<name>
        # and returns that path, so matters.json reuses the candidates file's parent.
        path = stage_json(candidates, name="candidates.json", out=out)
        stage_json(
            [m.model_dump(mode="json") for m in matters],
            name="matters.json",
            out=path.parent,
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(candidates)} enforcement candidate(s) to {path.parent}")


def _lawbrain_targets(wiki: Path) -> list[TargetRef]:
    """Read every tracked Bill + EnforcementAction page into a TargetRef.

    A TargetRef carries the deterministic key-set (``tracked_item_keys``) the
    law-brain matcher intersects against page keys. Malformed pages are skipped
    (per-page isolation; mirrors ``_existing_matters``). Both kinds participate:
    commentary attaches on a shared jurisdiction-qualified key regardless of
    ZwiadBrain page kind (D59).
    """
    targets: list[TargetRef] = []
    for page in sorted(wiki.glob("**/*.md")):
        try:
            item = from_page(page.read_text(encoding="utf-8"))
        except (WikiSchemaError, ConfigError):
            continue
        # from_page yields exactly Bill | EnforcementAction; the isinstance narrows
        # the else branch to EnforcementAction (both kinds participate, D59).
        kind: Literal["bill", "enforcement"] = (
            "bill" if isinstance(item, Bill) else "enforcement"
        )
        targets.append(
            TargetRef(
                id=item.id,
                kind=kind,
                jurisdiction=item.jurisdiction,
                title=item.title,
                keys=sorted(tracked_item_keys(item)),
            )
        )
    return targets


def _lawbrain_registry_path(wiki: Path) -> Path:
    """The committed link-decision registry lives beside the wiki (wiki/links.yaml)."""
    return wiki / "links.yaml"


def _is_marker_slug(slug: str, markers: list[str]) -> bool:
    """True when any fail-closed marker is a substring of the page slug (D60)."""
    return any(marker in slug for marker in markers)


def _summary_excerpt(body: str, *, limit: int = 280) -> str:
    """First non-heading paragraph of a law-brain page body, truncated for the matcher.

    Mirrors the ``text``-excerpt convention the enforcement candidates use to give the
    subagent a compact grounding snippet without shipping the whole body.
    """
    for block in body.split("\n\n"):
        stripped = block.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:limit]
    return ""


@app.command(name="fetch-lawbrain-candidates")
def fetch_lawbrain_candidates(
    wiki: Annotated[
        Path, typer.Option(help="Wiki root (for tracked targets).")
    ] = Path("wiki"),
    out: Annotated[
        Path | None, typer.Option(help="Run directory for lawbrain-candidates.json.")
    ] = None,
) -> None:
    """Read the law brain, match pages to tracked items by deterministic key, and
    stage lawbrain-candidates.json + targets.json for the interactive matcher.

    A clean no-op when the law brain is unavailable or disabled (``is_available``).
    One shared key -> deterministic ``link`` (conf 1.0); a key collision -> ``collision``
    (review); zero keys on a single-subject page -> ``keyless`` with a shortlist for the
    ``lawbrain-matcher`` subagent. Fail-closed slug-marker pages emit no keys and are
    skipped entirely (D60). Settled registry pages whose key-set is unchanged are
    skipped (D9). Mirrors fetch-enforcement-candidates.
    """
    try:
        settings = load_settings()
        law_brain_path = settings.effective_law_brain_path
        # A missing/disabled law brain (or no configured path) is a clean no-op,
        # never an error — exit 0 before staging anything.
        if not settings.lawbrain.enabled or law_brain_path is None:
            typer.echo("law brain unavailable or disabled; nothing to do")
            return
        reader = LawBrainReader(law_brain_path)
        if not reader.is_available():
            typer.echo("law brain unavailable or disabled; nothing to do")
            return
        targets = _lawbrain_targets(wiki) if wiki.exists() else []
        # Build a key -> target-ids index once. A page's match is the set of targets
        # sharing >=1 key with the page (set intersection over this index).
        index: dict[str, list[str]] = {}
        for target in targets:
            for key in target.keys:
                index.setdefault(key, []).append(target.id)
        registry = LinkRegistry.load(_lawbrain_registry_path(wiki))
        markers = settings.lawbrain.commentary_only_slug_markers
        candidates: list[dict[str, object]] = []
        for page in reader.pages():
            keys = page_keys(page, markers)
            # Fail-closed: a slug-marker (tracker/landscape/...) page emits zero keys.
            # Without a key it cannot deterministically attach; with no single subject
            # it must not go to the matcher either, so it is skipped entirely (D60).
            if not keys and _is_marker_slug(page.slug, markers):
                continue
            khash = keys_hash(keys)
            decided = registry.decision_for(page.slug)
            # Skip a settled page unless its freshly-extracted key-set differs (D9).
            if decided is not None and decided.keys_hash == khash:
                continue
            matched_ids = sorted({tid for key in keys for tid in index.get(key, [])})
            match: str
            target_id: str | None
            shortlist: list[str] | None
            if len(matched_ids) == 1:
                match, target_id, shortlist = "deterministic", matched_ids[0], None
            elif len(matched_ids) > 1:
                match, target_id, shortlist = "collision", None, matched_ids
            else:
                # Zero keys on a single-subject page -> the LLM matcher decides over a
                # jurisdiction-scoped shortlist (never the full corpus).
                match, target_id = "keyless", None
                shortlist = [t.id for t in build_shortlist(page, targets)]
            entry: dict[str, object] = {
                "slug": page.slug,
                "title": page.title,
                "type": page.type,
                "jurisdiction": page.jurisdiction,
                "tags": page.tags,
                "citation": page.citation,
                "summary_excerpt": _summary_excerpt(page.body),
                "keys": sorted(keys),
                "keys_hash": khash,
                "match": match,
                "target_id": target_id,
                "shortlist": shortlist,
            }
            candidates.append(entry)
        # Stage both files in the SAME run directory: stage_json returns the
        # candidates path, so targets.json reuses its parent (mirrors the
        # candidates.json/matters.json pairing in fetch-enforcement-candidates).
        path = stage_json(candidates, name="lawbrain-candidates.json", out=out)
        stage_json(
            [t.model_dump(mode="json") for t in targets],
            name="targets.json",
            out=path.parent,
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(candidates)} law-brain candidate(s) to {path.parent}")


def _opt_date(value: object) -> dt.date | None:
    """Parse an optional ISO date string from staging JSON (empty/None -> None)."""
    if not value:
        return None
    return dt.date.fromisoformat(str(value)[:10])


def _opt_str_e(value: object) -> str | None:
    """Coerce an optional staging-JSON scalar to a non-empty str (empty/None -> None)."""
    return str(value) if value not in (None, "") else None


def _str_map(value: object) -> dict[str, str]:
    """Coerce a staging-JSON object to a str->str map; non-dict input -> empty map.

    ``isinstance(value, dict)`` narrows to ``dict[Unknown, Unknown]`` (the JSON parse
    yields untyped keys/values), so ``str(k)``/``str(v)`` take Unknown arguments — the
    same staging-JSON traversal seam ``_as_list`` annotates with a per-line ignore.
    """
    if not isinstance(value, dict):
        return {}
    return {
        str(k): str(v)  # pyright: ignore[reportUnknownArgumentType]
        for k, v in value.items()  # pyright: ignore[reportUnknownVariableType]
    }


def _enforcement_page_by_id(wiki: Path, matter_id: str) -> Path | None:
    """Locate an existing enforcement page by matter id under any jurisdiction."""
    matches = list(wiki.glob(f"**/enforcement/{matter_id}.md"))
    return matches[0] if matches else None


@app.command(name="render-enforcement")
def render_enforcement(
    input_file: Annotated[Path, typer.Option("--in", help="classified.json to render.")],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path("data/cache/index.sqlite"),
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Build/consolidate enforcement matters from classified items and render them.

    A strong-key match is trusted; an LLM-proposed match is re-confirmed deterministically
    (D53) and demoted to a new page (with a possible-duplicate note) when the confirm
    fails — never a silent wrong-merge. Consolidation is idempotent (D20).
    """
    try:
        topic_keys = set(load_reference(topics).topic_keys)
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read classified file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"classified file must be a JSON list, got {type(raw).__name__}")
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        settings = load_settings()
        existing_ids = {m.id for m in (_existing_matters(wiki, settings) if wiki.exists() else [])}
        new_count = consolidated = flagged = 0
        notes: list[str] = []
        # Per-item isolation: a malformed entry (missing key, bad source_url, unknown
        # topic) is recorded as a drop and skipped, never fatal — one slipped LLM key
        # must not lose every well-formed item in the batch (mirrors render-leg-history).
        dropped: list[tuple[str, str]] = []
        for i, item in enumerate(entries):
            if not isinstance(item, dict):
                dropped.append((f"entry[{i}]", "classified entry is not a JSON object"))
                continue
            e: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
            identifier = str(e.get("title") or e.get("matter_id") or f"entry[{i}]")
            try:
                topics_list = [str(t) for t in _as_list(e.get("topics"), "topics")]
                unknown = [t for t in topics_list if t not in topic_keys]
                if unknown:
                    raise ConfigError(
                        f"enforcement item has unknown topic(s): {', '.join(unknown)}"
                    )
                development = EnforcementDevelopment.model_validate(e["development"])
                matter_id = e.get("matter_id")
                match_source = str(e.get("match_source") or "none")
                existing_page: EnforcementAction | None = None
                if matter_id:
                    page = _enforcement_page_by_id(wiki, str(matter_id))
                    if page is not None:
                        loaded = from_page(page.read_text(encoding="utf-8"))
                        if isinstance(loaded, EnforcementAction):
                            existing_page = loaded
                # Deterministic confirm of an LLM-proposed match (D53).
                if existing_page is not None and match_source == "llm":
                    ok = confirm_match(
                        item_respondent=_opt_str_e(e.get("respondent")),
                        item_date=_opt_date(e.get("date_filed")),
                        candidate_respondent=existing_page.respondent,
                        candidate_date=existing_page.date_filed,
                        confidence=float(e.get("match_confidence") or 0.0),  # pyright: ignore[reportArgumentType]
                        min_confidence=settings.enforcement.min_confidence,
                        window_days=settings.enforcement.match_window_days,
                    )
                    if not ok:
                        notes.append(
                            f"possible-duplicate-of: {matter_id} (failed confirm) "
                            f"-> new page for {e.get('respondent')!r}"
                        )
                        flagged += 1
                        existing_page = None  # fall through to new-matter path
                if existing_page is not None:
                    merged = merge_current_state(
                        existing_page,
                        status=_opt_str_e(e.get("status")),
                        date_resolved=_opt_date(e.get("date_resolved")),
                        penalties=_opt_str_e(e.get("penalties")),
                        outcome=_opt_str_e(e.get("outcome")),
                        significance=_opt_str_e(e.get("significance")),
                    )
                    # Body-prose fields are body-only (not persisted to frontmatter), so a
                    # reloaded existing_page has them as None. Re-apply the incoming item's
                    # prose monotonically (a null new value keeps the existing one), which
                    # also makes a repeated same-item render byte-identical (D20).
                    merged = merged.model_copy(update={
                        "summary": _opt_str_e(e.get("summary")) or existing_page.summary,
                        "background": _opt_str_e(e.get("background")) or existing_page.background,
                        "allegations": _opt_str_e(e.get("allegations"))
                        or existing_page.allegations,
                        "developments": merge_developments(
                            existing_page.developments, development
                        ),
                        "sources": {**existing_page.sources, **_str_map(e.get("sources"))},
                    })
                    write_page(merged, wiki)
                    consolidated += 1
                else:
                    year = (_opt_date(e.get("date_filed")) or dt.date.today()).year
                    new_id = build_enforcement_id(
                        str(e.get("agency_slug") or "unknown"),
                        strong_key=(str(e["strong_key"]) if e.get("strong_key") else None),
                        respondent=_opt_str_e(e.get("respondent")),
                        year=year,
                        existing_ids=existing_ids,
                    )
                    action = EnforcementAction(
                        id=new_id,
                        jurisdiction=str(e["jurisdiction"]),
                        title=str(e["title"]),
                        agency=str(e["agency"]),
                        topics=topics_list,
                        respondent=_opt_str_e(e.get("respondent")),
                        action_type=_opt_str_e(e.get("action_type")),
                        statutes=[str(s) for s in _as_list(e.get("statutes"), "statutes")],
                        penalties=_opt_str_e(e.get("penalties")),
                        status=_opt_str_e(e.get("status")),
                        docket=(str(e["strong_key"]) if e.get("strong_key") else None),
                        date_filed=_opt_date(e.get("date_filed")),
                        date_resolved=_opt_date(e.get("date_resolved")),
                        summary=_opt_str_e(e.get("summary")),
                        background=_opt_str_e(e.get("background")),
                        allegations=_opt_str_e(e.get("allegations")),
                        outcome=_opt_str_e(e.get("outcome")),
                        significance=_opt_str_e(e.get("significance")),
                        developments=[development],
                        sources=_str_map(e.get("sources")),
                    )
                    write_page(action, wiki)
                    # Reserve the id only after a successful write, so a dropped item
                    # below does not leave a phantom id reserved against the batch.
                    existing_ids.add(new_id)
                    new_count += 1
            except (KeyError, ValidationError, ConfigError, ValueError) as exc:
                dropped.append((identifier, str(exc)))
                continue
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"enforcement: {new_count} new / {consolidated} consolidated"
        f" / {flagged} flagged / {len(dropped)} dropped"
    )
    for note in notes:
        typer.echo(f"  {note}")
    for ident, reason in dropped:
        typer.echo(f"  dropped: {ident} — {reason}")


def _lawbrain_page_by_id(wiki: Path, target_id: str) -> Path | None:
    """Locate an existing tracked page (bill OR enforcement) by id under any jurisdiction.

    Commentary attaches regardless of page kind (D59), so both wiki subtrees are
    searched; the first match wins (ids are unique across the wiki).
    """
    matches = list(wiki.glob(f"**/bills/{target_id}.md")) + list(
        wiki.glob(f"**/enforcement/{target_id}.md")
    )
    return matches[0] if matches else None


def _lawbrain_page_by_slug(reader: LawBrainReader, slug: str) -> LawBrainPage | None:
    """Return the parsed law-brain page with this slug, or None if it is gone (stale)."""
    return next((p for p in reader.pages() if p.slug == slug), None)


def _resolve_review_queue(
    queue_path: Path,
    new_entries: list[ReviewEntry],
    registry: LinkRegistry,
    notes: list[str],
) -> None:
    """Apply operator-resolved queue tokens, then write the merged pending queue (D61).

    Reads the existing ``review-queue.md`` (if any): an ``[accept]`` entry is
    recorded in the registry as a ``link`` override (the actual copy happens on the
    NEXT sync run, when the page re-enters classified.json with the override in
    place — the same two-pass shape the fetch half relies on), a ``[reject]`` entry
    is recorded as a ``reject`` decision. Resolved entries are pruned; unresolved
    ``[pending]`` entries plus this run's new proposals are written back, deduped by
    ``(slug, target_id, reason)``.
    """
    existing: list[ReviewEntry] = []
    if queue_path.exists():
        existing = parse_review_queue(queue_path.read_text(encoding="utf-8"))
    pending: list[ReviewEntry] = []
    for entry in existing:
        if entry.status == "accept":
            registry.record(
                LinkDecision(
                    lawbrain_slug=entry.slug,
                    decision="link",
                    target_id=entry.target_id,
                    matched_by="llm",
                    keys_hash="",  # operator override; re-evaluated on the next sync (D9)
                    decided=dt.date.today(),
                )
            )
            notes.append(f"accepted: {entry.slug} -> {entry.target_id}")
        elif entry.status == "reject":
            registry.record(
                LinkDecision(
                    lawbrain_slug=entry.slug,
                    decision="reject",
                    target_id=entry.target_id,
                    matched_by=None,
                    keys_hash="",
                    decided=dt.date.today(),
                )
            )
            notes.append(f"rejected: {entry.slug}")
        else:
            pending.append(entry)
    seen: set[tuple[str, str | None, str]] = set()
    merged: list[ReviewEntry] = []
    for entry in [*pending, *new_entries]:
        key = (entry.slug, entry.target_id, entry.reason)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    if merged:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(render_review_queue(merged), encoding="utf-8", newline="\n")
    elif queue_path.exists():
        # All resolved — leave an empty queue file (committed, transient) so the
        # operator sees the cleared state rather than a stale list.
        queue_path.write_text(render_review_queue([]), encoding="utf-8", newline="\n")


@app.command(name="render-lawbrain-commentary")
def render_lawbrain_commentary(
    input_file: Annotated[
        Path, typer.Option("--in", help="classified.json of decided law-brain links.")
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write commentary onto.")] = Path(
        "wiki"
    ),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path(
        "data/cache/index.sqlite"
    ),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print intended writes; make zero edits.")
    ] = False,
) -> None:
    """Render law-brain commentary onto tracked pages — the render half of /zwiad-sync-lawbrain.

    A ``deterministic`` link is trusted; an ``llm`` link is re-grounded by
    :func:`lawbrain_confirm_match` (require >=1 shared jurisdiction-qualified key, D16)
    and demoted to a ``weak-grounding`` review-queue entry when the confirm fails —
    never a silent topical merge. For each applied link the matched page body is copied
    verbatim and its secondary reference links harvested (D62) into the target's
    ``commentary_sources``; the renderer rebuilds the ``lawbrain:region`` authoritatively
    from those fresh bodies (D63). Operator-resolved queue tokens (``[accept]``/
    ``[reject]``) are applied in the same pass (D61). Idempotent; ``--dry-run`` is read-only.
    """
    try:
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read classified file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"classified file must be a JSON list, got {type(raw).__name__}")
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        settings = load_settings()
        reader = LawBrainReader(settings.effective_law_brain_path or Path("."))
        if not (settings.lawbrain.enabled and reader.is_available()):
            typer.echo("lawbrain: disabled or unavailable — no-op")
            raise typer.Exit(0)

        registry_path = wiki / "links.yaml"
        queue_path = wiki / "review-queue.md"
        registry = LinkRegistry.load(registry_path)
        # Cache the live law-brain slug set once; staleness is checked per target.
        live_slugs = {p.slug for p in reader.pages()}
        review: list[ReviewEntry] = []
        linked = reviewed = 0
        notes: list[str] = []
        intended: list[str] = []  # dry-run preview lines
        # Per-item isolation: a malformed entry is recorded as a drop and skipped,
        # never fatal — mirrors render-enforcement.
        dropped: list[tuple[str, str]] = []
        recorded = 0  # not_in_scope/reject decisions recorded (no attach)
        for i, item in enumerate(entries):
            if not isinstance(item, dict):
                dropped.append((f"entry[{i}]", "classified entry is not a JSON object"))
                continue
            e: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
            slug = str(e.get("slug") or f"entry[{i}]")
            try:
                slug = str(e["slug"])
                matched_by = str(e["matched_by"])
                page_key_set = {str(k) for k in _as_list(e.get("page_keys"), "page_keys")}
                # A not_in_scope/reject decision attaches nothing — it is recorded in
                # links.yaml so the page is never re-proposed (sticky, D9). target_id
                # is optional for these (the subagent may resolve a keyless page to
                # not_in_scope with no target).
                if matched_by in ("not_in_scope", "reject"):
                    new_decision: Literal["not_in_scope", "reject"] = (
                        "not_in_scope" if matched_by == "not_in_scope" else "reject"
                    )
                    if dry_run:
                        intended.append(f"record {matched_by} {slug}")
                    else:
                        # Preserve the prior decided date when this exact decision is
                        # re-recorded unchanged, so links.yaml is byte-identical across
                        # day boundaries (the "idempotent" contract, D20).
                        prior = registry.decision_for(slug)
                        decided_date = (
                            prior.decided
                            if (prior is not None and prior.decision == new_decision)
                            else dt.date.today()
                        )
                        registry.record(
                            LinkDecision(
                                lawbrain_slug=slug,
                                decision=new_decision,
                                target_id=_opt_str_e(e.get("target_id")),
                                matched_by=None,
                                keys_hash=keys_hash(page_key_set),
                                decided=decided_date,
                            )
                        )
                    recorded += 1
                    continue
                if matched_by not in ("deterministic", "llm"):
                    raise ConfigError(f"unknown matched_by {matched_by!r}")
                target_id = str(e["target_id"])
                # mypy/pyright: narrow to the build_commentary_source Literal.
                matched_by_lit: Literal["deterministic", "llm"] = (
                    "deterministic" if matched_by == "deterministic" else "llm"
                )
                confidence = float(e["confidence"])  # pyright: ignore[reportArgumentType]
                decided = registry.decision_for(slug)
                override = decided is not None and decided.decision == "link"
                # Load the fresh law-brain page + tracked target FIRST so the confirm
                # grounds against real disk state, never the LLM-echoed keys carried in
                # classified.json (D16): an untrusted proposal could echo intersecting
                # fake keys. The keys are RECOMPUTED here from the freshly-read page and
                # target, and these recomputed sets drive both the confirm gate and the
                # stored keys_hash (registry stickiness must reflect real keys, D9).
                page = _lawbrain_page_by_slug(reader, slug)
                if page is None:
                    # Source vanished from the law brain: do not attach; flag stale.
                    review.append(
                        ReviewEntry(slug=slug, target_id=target_id, reason="stale")
                    )
                    reviewed += 1
                    continue
                target_path = _lawbrain_page_by_id(wiki, target_id)
                if target_path is None:
                    raise ConfigError(f"target page not found in wiki: {target_id}")
                loaded = from_page(target_path.read_text(encoding="utf-8"))
                page_key_set = page_keys(
                    page, settings.lawbrain.commentary_only_slug_markers
                )
                target_key_set = tracked_item_keys(loaded)
                shared_key = len(page_key_set & target_key_set) >= 1
                # An LLM proposal is re-grounded by the deterministic confirm (D16). A
                # deterministic link was key-grounded by the fetch half, but classified.json
                # can go stale (the page or target changed since fetch), so re-verify the
                # shared-key intersection against the fresh keys and route to review if it
                # no longer holds rather than attaching on a now-broken match.
                if matched_by == "llm":
                    ok = lawbrain_confirm_match(
                        page_keys=page_key_set,
                        target_keys=target_key_set,
                        confidence=confidence,
                        min_confidence=settings.lawbrain.min_confidence,
                        require_shared_key=settings.lawbrain.require_shared_key,
                        override=override,
                    )
                    if not ok:
                        review.append(
                            ReviewEntry(
                                slug=slug, target_id=target_id, reason="weak-grounding"
                            )
                        )
                        reviewed += 1
                        continue
                elif (
                    settings.lawbrain.require_shared_key and not override and not shared_key
                ):
                    # Deterministic link whose fresh keys no longer intersect (stale
                    # classified.json). Do not attach on a broken match — flag for review.
                    review.append(
                        ReviewEntry(slug=slug, target_id=target_id, reason="weak-grounding")
                    )
                    reviewed += 1
                    continue
                memo_texts = [
                    t
                    for rel in page.source_files
                    if (t := reader.read_source_memo(rel)) is not None
                ]
                links = harvest_links(
                    page_body=page.body,
                    memo_texts=memo_texts,
                    primary_source_domains=settings.lawbrain.primary_source_domains,
                )
                source = build_commentary_source(
                    page=page,
                    matched_by=matched_by_lit,
                    confidence=confidence,
                    links=(links if settings.lawbrain.further_reading else []),
                )
                merged_sources = merge_commentary(loaded.commentary_sources, source)
                updated_item = loaded.model_copy(
                    update={"commentary_sources": merged_sources}
                )
                # Staleness: any prior commentary slug no longer live in the law brain.
                for stale_slug in detect_stale(merged_sources, live_slugs):
                    review.append(
                        ReviewEntry(
                            slug=stale_slug, target_id=target_id, reason="stale"
                        )
                    )
                    notes.append(f"stale: {stale_slug} on {target_id} (kept, flagged)")
                if dry_run:
                    intended.append(
                        f"link {slug} -> {target_id} ({matched_by}, {len(links)} links)"
                    )
                else:
                    # Attach the region in place — never re-render the body, which would
                    # drop a bill's body-only Summary/Status & Timeline/Full Text (D63).
                    write_lawbrain_region(updated_item, wiki)
                    # Preserve the prior decided date on an unchanged link re-record so
                    # links.yaml stays byte-identical across days (D20). `decided` is the
                    # registry decision read above for the override check.
                    decided_date = (
                        decided.decided
                        if (decided is not None and decided.decision == "link")
                        else dt.date.today()
                    )
                    registry.record(
                        LinkDecision(
                            lawbrain_slug=slug,
                            decision="link",
                            target_id=target_id,
                            matched_by=matched_by,
                            keys_hash=keys_hash(page_key_set),
                            decided=decided_date,
                        )
                    )
                linked += 1
            except (KeyError, ValidationError, ConfigError, ValueError, WikiSchemaError) as exc:
                dropped.append((slug, str(exc)))
                continue

        if dry_run:
            typer.echo(
                f"lawbrain (dry-run): {linked} would link / {recorded} recorded"
                f" / {reviewed} review / {len(dropped)} dropped"
            )
            for line in intended:
                typer.echo(f"  would: {line}")
            for ident, reason in dropped:
                typer.echo(f"  dropped: {ident} — {reason}")
            raise typer.Exit(0)

        # Apply operator-resolved queue tokens AND merge the new proposals (D61),
        # then persist the registry and reindex. _resolve_review_queue may record
        # accept/reject decisions, so it runs before the dump decision.
        registry_changed = linked > 0 or recorded > 0
        notes_before = len(notes)
        _resolve_review_queue(queue_path, review, registry, notes)
        # A queue resolution that recorded an accept/reject appends a note.
        registry_changed = registry_changed or len(notes) > notes_before
        # Persist the registry when this run recorded a decision, or to refresh an
        # already-committed registry (idempotent: dump is a stable slug-sorted write).
        if registry_changed or registry_path.exists():
            registry.dump(registry_path)
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"lawbrain: {linked} linked / {recorded} recorded / {reviewed} review"
        f" / {len(dropped)} dropped"
    )
    for note in notes:
        typer.echo(f"  {note}")
    for ident, reason in dropped:
        typer.echo(f"  dropped: {ident} — {reason}")


def _as_list(value: object, key: str) -> list[object]:
    """Coerce a staging-JSON field to a list of items.

    A missing field (``None``) — including a present-but-``null`` field — becomes
    an empty list, so ``enumerate`` does not raise ``TypeError`` past the
    ``AppError`` handler.  Any other non-list type is a malformed staging file and
    raises :class:`ConfigError`.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"staging file '{key}' must be a list, got {type(value).__name__}")
    # `value` is list[Unknown] after the isinstance narrow; rebuild as list[object] so
    # callers iterate typed `object` items (each then validated/narrowed at use).
    items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    return items


def _fetch_url(url: str) -> tuple[int, str]:
    """Fetch a URL for grounding; returns (status_code, body_text).

    Never raises — returns (0, '') on any HTTP error or on a malformed
    researcher-supplied URL (``httpx.InvalidURL``, which is NOT an HTTPError
    subclass and would otherwise crash the whole render).
    """
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        return (resp.status_code, resp.text)
    except (httpx.HTTPError, httpx.InvalidURL):
        return (0, "")


@app.command(name="render-leg-history")
def render_leg_history(
    input_file: Annotated[
        Path, typer.Option("--in", help="leghistory staging JSON to ground and render.")
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
) -> None:
    """Ground researched statements/hearings, assemble final leg history, and render the page."""
    try:
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read staging file {input_file}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConfigError(f"staging file must be a JSON object, got {type(raw).__name__}")

        payload: dict[str, object] = raw  # type: ignore[assignment]

        if "bill" not in payload:
            raise ConfigError("staging file is missing required key 'bill'")
        if "spine" not in payload:
            raise ConfigError("staging file is missing required key 'spine'")

        bill = validate_model(Bill, payload["bill"], label="bill")
        spine = validate_model(LegHistory, payload["spine"], label="spine")

        # Per-item parse: collect validation failures as parse-drops instead of aborting.
        # `_as_list` coerces a present-but-null JSON field to [] rather than None, which
        # would raise TypeError past the AppError handler (a null statements/hearings/
        # verdicts field is real researcher output, not a programming error).
        #
        # original_indices tracks each surviving statement's position in the raw input list.
        # This is required for verdict remapping (see below): when an earlier item parse-drops,
        # surviving items shift position, and verdicts keyed by original index must be remapped
        # to the new surviving-list positions before being passed to ground_items.
        parse_dropped_statements: list[tuple[str, str]] = []
        statements: list[Statement] = []
        original_indices: list[int] = []
        for i, item in enumerate(_as_list(payload.get("statements"), "statements")):
            try:
                statements.append(Statement.model_validate(item))
                original_indices.append(i)
            except ValidationError as exc:
                parse_dropped_statements.append((f"statement[{i}]", str(exc)))

        parse_dropped_hearings: list[tuple[str, str]] = []
        hearings: list[Hearing] = []
        for i, item in enumerate(_as_list(payload.get("hearings"), "hearings")):
            try:
                hearings.append(Hearing.model_validate(item))
            except ValidationError as exc:
                parse_dropped_hearings.append((f"hearing[{i}]", str(exc)))

        narrative_raw = payload.get("narrative")
        if narrative_raw is not None and not isinstance(narrative_raw, str):
            raise ConfigError(
                f"staging file 'narrative' must be a string, got {type(narrative_raw).__name__}"
            )
        narrative = narrative_raw

        # Build verdicts_by_original keyed by each entry's self-reported original index.
        # These indices refer to positions in the FULL raw statements list (before parse-drops).
        # Each verdict carries the verifier's echo of what it checked (speaker +
        # quote_prefix). We store the verdict alongside the echo so the remap step
        # can fail-closed when the echo does not match the statement at that index.
        verdicts_by_original: dict[int, tuple[bool, str, str]] = {}
        for v in _as_list(payload.get("verdicts"), "verdicts"):
            if not isinstance(v, dict):
                raise ConfigError("each entry in 'verdicts' must be a JSON object")
            verdict: dict[str, object] = v  # pyright: ignore[reportUnknownVariableType]
            index = verdict.get("index")
            if not isinstance(index, int):
                raise ConfigError(f"verdict 'index' must be an integer, got {type(index).__name__}")
            echo_speaker = verdict.get("speaker")
            echo_prefix = verdict.get("quote_prefix")
            verdicts_by_original[index] = (
                bool(verdict.get("verified")),
                echo_speaker if isinstance(echo_speaker, str) else "",
                echo_prefix if isinstance(echo_prefix, str) else "",
            )

        # Remap verdicts from original-index space to surviving-position space.
        # ground_items keys verdicts by position in the list it receives (enumerate contract).
        # When an earlier statement parse-drops, surviving statements shift position, so
        # verdicts[original_i] must become verifier_verdicts[new_pos] where new_pos is the
        # index of that statement in the surviving `statements` list.
        # A missing original index in verdicts_by_original counts as not-verified (False),
        # matching ground_items' own default for a missing key.
        #
        # Remap to surviving-position space AND cross-check the verifier's echo
        # against the statement it claims to have scored. A mismatched echo means
        # the verifier scored a different (or shifted) statement than we think, so
        # we downgrade verified -> False (fail-closed) rather than trust it.
        verifier_verdicts: dict[int, bool] = {}
        for new_pos, orig_idx in enumerate(original_indices):
            verified, echo_speaker, echo_prefix = verdicts_by_original.get(
                orig_idx, (False, "", "")
            )
            if verified:
                stmt = statements[new_pos]
                speaker_ok = echo_speaker == stmt.speaker
                prefix_ok = bool(echo_prefix) and stmt.quote.startswith(echo_prefix)
                if not (speaker_ok and prefix_ok):
                    verified = False
            verifier_verdicts[new_pos] = verified

        result = ground_items(
            statements, hearings, fetch=_fetch_url, verifier_verdicts=verifier_verdicts
        )

        final = spine.model_copy(
            update={
                "hearings": list(result.hearings),
                "statements": list(result.statements),
                "narrative": narrative,
            }
        )
        bill = bill.model_copy(update={
            "leg_history": final,
            "summary_hash": summary_hash(bill.summary),
            "amendments_count": len(bill.amendments),
        })

        written = write_page(bill, wiki)

        # ------------------------------------------------------------------ #
        # Summary line
        # ------------------------------------------------------------------ #
        enacted_str = "enacted=yes" if (final.enactment is not None) else "enacted=no"
        spine_summary = (
            f"versions={len(final.versions)}"
            f" committee_reports={len(final.committee_reports)}"
            f" votes={len(final.votes)}"
            f" floor={len(final.floor_consideration)}"
            f" {enacted_str}"
        )
        # Counts reconcile against ALL input items: parse-dropped items never reach
        # the grounding gate, so they are tracked separately from ground-drops.
        stmt_parse_drops = len(parse_dropped_statements)
        stmt_grounded = len(result.statements)
        stmt_ground_drops = len(statements) - stmt_grounded
        stmt_input = stmt_grounded + stmt_ground_drops + stmt_parse_drops

        hearing_parse_drops = len(parse_dropped_hearings)
        hearing_kept = len(result.hearings)
        hearing_ground_drops = len(hearings) - hearing_kept
        hearing_input = hearing_kept + hearing_ground_drops + hearing_parse_drops

        page_status = "written" if written else "unchanged"
        typer.echo(
            f"{bill.id}: {spine_summary} | "
            f"statements: {stmt_input} input / {stmt_grounded} grounded"
            f" / {stmt_parse_drops} parse-drop / {stmt_ground_drops} ground-drop | "
            f"hearings: {hearing_input} input / {hearing_kept} grounded"
            f" / {hearing_parse_drops} parse-drop / {hearing_ground_drops} ground-drop | "
            f"narrative={'yes' if narrative else 'no'} | "
            f"page {page_status}"
        )

        # ------------------------------------------------------------------ #
        # Per-drop audit lines
        # ------------------------------------------------------------------ #
        for identifier, reason in parse_dropped_statements:
            typer.echo(f"  dropped statement: {identifier} — {reason}")
        for identifier, reason in parse_dropped_hearings:
            typer.echo(f"  dropped hearing: {identifier} — {reason}")
        for d in result.dropped:
            typer.echo(f"  dropped {d.kind}: {d.identifier} — {d.reason}")

    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command(name="run-log")
def run_log(
    input_file: Annotated[
        Path, typer.Option("--in", help="run-summary JSON assembled by /zwiad-run.")
    ],
    log_file: Annotated[
        Path, typer.Option(help="Committed append-only scan log.")
    ] = Path("scan-log.md"),
    at: Annotated[
        str | None,
        typer.Option(help="ISO timestamp override (tests); defaults to now (UTC)."),
    ] = None,
) -> None:
    """Append one grep-parseable block to scan-log.md — the audit half of /zwiad-run."""
    try:
        raw = json.loads(input_file.read_text(encoding="utf-8"))
        summary = RunSummary.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        typer.echo(f"error: invalid run-summary {input_file}: {exc}", err=True)
        raise typer.Exit(1) from exc
    when = dt.datetime.fromisoformat(at) if at else dt.datetime.now(dt.UTC)
    append_run_log(log_file, format_run_log_entry(summary, when))
    typer.echo(f"run-log: appended {summary.run_id} ({len(summary.sources)} sources)")


def main() -> None:
    """Console-script entry point.

    Force UTF-8 on stdout/stderr before dispatching: command help text and echoed
    messages contain non-ASCII (em dashes, the IN->OUT arrow), which raise
    ``UnicodeEncodeError`` on a legacy Windows console (cp1252). Reconfiguring to
    UTF-8 avoids the crash; the guard makes it a no-op where a stream cannot be
    reconfigured (e.g. a captured test buffer).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
