"""ZwiadBrain command-line interface.

These are the deterministic fetch/render halves that the interactive Claude Code
slash commands drive (the subagents run between a fetch and a render; Python
makes no LLM calls — DECISIONS.md D26/D27). Commands:

- ``version`` / ``reindex`` — utilities.
- ``backfill`` — deterministic discover→enrich→render (no classification).
- ``fetch-candidates`` / ``render-classified`` — the ``/zwiad-backfill`` halves.
- ``fetch-enacted-candidates`` — enacted-only federal discovery for ``/zwiad-backfill-enacted``
  (D84).
- ``fetch-leg-history`` / ``render-leg-history`` — the ``/zwiad-leg-history`` halves.
- ``fetch-refreshable`` / ``render-refreshed`` — the ``/zwiad-refresh`` halves.
- ``fetch-state-candidates`` / ``fetch-state-refreshable`` — ``/zwiad-scan-states``.
- ``fetch-state-enacted-candidates`` — enacted-only state discovery for
  ``/zwiad-backfill-enacted-state`` (D84).
- ``fetch-enforcement-candidates`` / ``render-enforcement`` — ``/zwiad-scan-enforcement``.
- ``fetch-lawbrain-candidates`` / ``render-lawbrain-commentary`` — ``/zwiad-sync-lawbrain``.

See ``ARCHITECTURE.md`` for the full command list and the slash commands they back.
"""

import contextlib
import datetime as dt
import json
import logging
import sys
import tempfile
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
    RelatedMedia,
    Statement,
)
from zwiadbrain.pipeline.discover import (
    dedupe_companions,
    filter_unseen,
    keyword_filter,
    recall_filter,
)
from zwiadbrain.pipeline.docling_text import docling_available, extract_markdown
from zwiadbrain.pipeline.enforcement import (
    MatterRef,
    confirm_match,
    merge_current_state,
    merge_developments,
)
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.pipeline.extract import extract_item, plan_extraction
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
from zwiadbrain.pipeline.leg_history import (
    LANE_ORDER,
    assemble_spine,
    assemble_state_spine,
    collect_leads,
    collect_state_leads,
    dedup_statements,
    ground_items,
    ground_related,
    merge_lanes,
    reground_with_render,
)
from zwiadbrain.pipeline.playwright_render import playwright_available, render_page_html
from zwiadbrain.pipeline.refresh import (
    apply_classifier_flip,
    clear_flip,
    detect_refreshable,
    detect_state_refreshable,
    preserve_leg_history,
    summary_hash,
)
from zwiadbrain.pipeline.rejects import (
    federal_bill_entry,
    federal_cursor,
    federal_key,
    filter_by_key,
    filter_cached_rejects,
    load_reject_ledger,
    split_stale_rejects,
    state_bill_entry,
    state_cursor,
    state_key,
    write_reject_ledger,
)
from zwiadbrain.pipeline.render import write_lawbrain_region, write_page
from zwiadbrain.pipeline.run_log import RunSummary, append_run_log, format_run_log_entry
from zwiadbrain.pipeline.staging import stage_json, validate_model
from zwiadbrain.pipeline.verdicts import Verdict, apply_summaries, split_by_verdict
from zwiadbrain.reference.loader import load_reference
from zwiadbrain.sources.base import Candidate
from zwiadbrain.sources.congress import CongressSource
from zwiadbrain.sources.enforcement.base import EnforcementSource
from zwiadbrain.sources.enforcement.ftc import FTCSource
from zwiadbrain.sources.enforcement.state_ag import StateAGSource
from zwiadbrain.sources.govinfo import GovInfoSource
from zwiadbrain.sources.lawbrain import LawBrainPage, LawBrainReader
from zwiadbrain.sources.legiscan import LegiScanSource
from zwiadbrain.sources.transcripts import make_gate_fetch, memoize_fetch
from zwiadbrain.store import Store
from zwiadbrain.wiki.schema import from_page

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TOPICS = Path("reference/topics.yaml")
_SCAN_LIMIT = 250  # bills to scan per fetch-candidates run (Congress list single-request max)
_MAX_PROBE = 250  # max Stage-2 policyArea probes per run (PHASE-03.1)
_STATE_OVERSAMPLE = 5  # over-fetch factor so --skip-existing still yields up to `limit` fresh bills

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


def _existing_federal_bill_ids(wiki: Path) -> set[str]:
    """Bill-id slugs already tracked under ``wiki/federal/bills`` (PHASE-22, --skip-existing).

    Each federal bill page is named ``<bill-id>.md`` (e.g. ``118-hr-2670.md``), so the file
    stems are exactly the bill ids :func:`filter_unseen` compares against. Missing directory
    -> empty set (nothing tracked yet).
    """
    bills_dir = wiki / "federal" / "bills"
    if not bills_dir.exists():
        return set()
    return {p.stem for p in bills_dir.glob("*.md")}


def _existing_state_bill_ids(wiki: Path, state: str) -> set[str]:
    """LegiScan bill ids already tracked under ``wiki/states/<st>/bills`` (--skip-existing).

    State page filenames are slugs (``ca-2025-ab-1064``), not LegiScan ids, so the
    discovery-time key (the LegiScan ``bill_id``) is read from each page's frontmatter via
    :func:`from_page`. ``.text.md`` sidecars are skipped; a missing directory -> empty set.
    """
    bills_dir = wiki / "states" / state / "bills"
    if not bills_dir.exists():
        return set()
    known: set[str] = set()
    for page in bills_dir.glob("*.md"):
        if page.name.endswith(".text.md"):
            continue
        try:
            item = from_page(page.read_text(encoding="utf-8"))
        except WikiSchemaError:
            typer.echo(f"skip-existing: skipping unreadable page {page}", err=True)
            continue
        if isinstance(item, Bill) and item.legiscan_bill_id is not None:
            known.add(str(item.legiscan_bill_id))
    return known


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
    max_pages: Annotated[
        int,
        typer.Option(
            min=1,
            help="Opt-in back-catalog sweep: max offset pages to scan (default 1 = newest only).",
        ),
    ] = 1,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop candidates that already have a wiki page (idempotent re-runs).",
        ),
    ] = False,
    wiki: Annotated[
        Path, typer.Option(help="Wiki root, for --skip-existing.")
    ] = Path("wiki"),
) -> None:
    """Fetch keyword-matched federal candidates and stage them for classification.

    The deterministic first half of the LLM pipeline: discover -> keyword recall
    filter -> enrich, writing fully-fetched ``Bill``s to ``candidates.json`` for
    the interactive session's classifier/summarizer subagents to consume.

    ``--max-pages`` opts into a bounded back-catalog offset sweep past the newest page
    (PHASE-22); ``--skip-existing`` drops bills already tracked in ``--wiki`` so a re-run
    does not re-stage them. Both default off, leaving the standard single-page behaviour.
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
        scanned = source.discover(congress=congress, limit=_SCAN_LIMIT, max_pages=max_pages)
        if skip_existing:
            known = _existing_federal_bill_ids(wiki)
            ledger = load_reject_ledger(wiki / ".rejects" / "federal.json")
            before = len(scanned)
            scanned = filter_unseen(scanned, known)
            after_unseen = len(scanned)
            scanned = filter_cached_rejects(
                scanned, ledger, key_of=federal_key, cursor_of=federal_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(scanned)} cached-reject of {before} scanned"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
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


@app.command(name="fetch-enacted-candidates")
def fetch_enacted_candidates(
    congress: Annotated[int, typer.Option(min=1, help="Congress number, e.g. 118.")],
    limit: Annotated[
        int, typer.Option(min=1, help="Max in-scope candidates to stage (recall output cap).")
    ] = 250,
    max_pages: Annotated[
        int,
        typer.Option(min=1, help="Pages of the enacted-law list to sweep (covers a full congress)."),  # noqa: E501
    ] = 5,
    classify_all: Annotated[
        bool,
        typer.Option(
            "--classify-all/--no-classify-all",
            help="Skip the recall pre-filter; stage every enacted law for classification.",
        ),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop enacted laws already tracked or in the reject ledger.",
        ),
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
) -> None:
    """Fetch a congress's ENACTED public laws and stage the in-scope ones for classification.

    Enacted-first discovery half of ``/zwiad-backfill-enacted`` (D84): ``/law/{congress}/pub``
    lists only enacted public laws, so non-enacted bills never enter the pipeline. By default
    the two-stage ``recall_filter`` (title seeds + ``policyArea`` probe over the *whole* enacted
    set) keeps the topically-relevant laws and the classifier subagent gates the survivors.
    ``--classify-all`` skips recall and stages every enacted law (zero recall risk, ~6x more
    enrichment + classifier work).
    """
    try:
        api_key = load_settings().require_congress_api_key()
        source = CongressSource(api_key)
        scanned = source.discover_laws(congress, limit=_SCAN_LIMIT, max_pages=max_pages)
        if skip_existing:
            known = _existing_federal_bill_ids(wiki)
            ledger = load_reject_ledger(wiki / ".rejects" / "federal.json")
            before = len(scanned)
            scanned = filter_unseen(scanned, known)
            after_unseen = len(scanned)
            scanned = filter_cached_rejects(
                scanned, ledger, key_of=federal_key, cursor_of=federal_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(scanned)} cached-reject of {before} enacted laws"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        if classify_all:
            candidates = scanned[:limit]
        else:
            reference = load_reference(topics)
            seeds, policy_areas = reference.seeds, reference.policy_areas
            candidates = recall_filter(
                scanned,
                source,
                seeds=seeds,
                policy_areas=policy_areas,
                limit=limit,
                max_probe=len(scanned),  # probe the WHOLE enacted set — recall not truncated
            )
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} enacted candidate(s) to {path}")


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


@app.command(name="record-rejects")
def record_rejects(
    input_file: Annotated[Path, typer.Option("--in", help="Out-of-scope bills JSON (Bill list).")],
    scope: Annotated[str, typer.Option(help="federal or state.")],
    cache_dir: Annotated[
        Path, typer.Option(help="Reject-ledger directory.")
    ] = Path("wiki/.rejects"),
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Record classified-out bills into the committed reject ledger (the negative cache).

    The write half that pairs with ``--skip-existing``: the interactive session hands back the
    OUT-of-scope ``Bill``s; this derives each one's change cursor and upserts it into
    ``<cache_dir>/<scope>.json`` so a future sweep skips it until the bill changes (D82).
    Each entry is stamped with the taxonomy's current ``scope_version`` so a later scope-rule
    change can surface it via ``stale-rejects`` (D96).
    """
    try:
        if scope not in {"federal", "state"}:
            raise ConfigError(f"--scope must be 'federal' or 'state', got {scope!r}")
        scope_version = load_reference(topics).scope_version
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read rejects file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"rejects file must be a JSON list, got {type(raw).__name__}")
        items: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        bills = [validate_model(Bill, item, label="reject bill") for item in items]
        entry_of = federal_bill_entry if scope == "federal" else state_bill_entry
        path = cache_dir / f"{scope}.json"
        ledger = load_reject_ledger(path)
        new = updated = 0
        for bill in bills:
            key, entry = entry_of(bill, scope_version=scope_version)
            if key in ledger:
                updated += 1
            else:
                new += 1
            ledger[key] = entry
        write_reject_ledger(path, ledger)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"recorded {new} new, {updated} updated reject(s) to {path}")


@app.command(name="stale-rejects")
def stale_rejects(
    scope: Annotated[str, typer.Option(help="federal or state.")],
    cache_dir: Annotated[
        Path, typer.Option(help="Reject-ledger directory.")
    ] = Path("wiki/.rejects"),
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
    key: Annotated[
        list[str] | None,
        typer.Option("--key", help="Ledger key to select explicitly (repeatable)."),
    ] = None,
    include_unknown: Annotated[
        bool,
        typer.Option(
            "--include-unknown",
            help="Treat pre-versioning entries (no scope_version) as stale for --clear.",
        ),
    ] = False,
    clear: Annotated[
        bool, typer.Option("--clear", help="Remove the selected stale entries from the ledger.")
    ] = False,
) -> None:
    """Surface (and optionally clear) reject-ledger entries recorded under superseded scope rules.

    The reject ledger is invalidated by BILL changes only; a scope-RULE change (e.g. D95)
    would otherwise strand entries forever. This command compares each entry's stamped
    ``scope_version`` against the taxonomy's current one: a mismatch is *stale*, a missing
    stamp is *unknown* (pre-versioning). ``--clear`` removes stale entries so the next
    sweep re-classifies them. Unknown entries are bulk-cleared only under
    ``--include-unknown`` — without that guard a single ``--clear`` would queue every
    pre-versioning reject (~1k bills, ~13k classifier tokens each) for re-classification.
    Explicit ``--key`` selections are always honored, whatever their stamp (D96).
    """
    try:
        if scope not in {"federal", "state"}:
            raise ConfigError(f"--scope must be 'federal' or 'state', got {scope!r}")
        current = load_reference(topics).scope_version
        path = cache_dir / f"{scope}.json"
        ledger = load_reject_ledger(path)
        stale, unknown = split_stale_rejects(ledger, current)
        if key:
            missing = [k for k in key if k not in ledger]
            if missing:
                raise ConfigError(f"--key not in {path}: {', '.join(missing)}")
            selected = list(key)
        else:
            selected = stale + (unknown if include_unknown else [])
        typer.echo(
            f"{path}: {len(ledger)} entries — {len(stale)} stale (scope_version != "
            f"{current!r}), {len(unknown)} unknown (pre-versioning)"
        )
        for k in selected:
            entry = ledger[k]
            label = entry.id or "-"
            typer.echo(f"  {k}  id={label}  scope_version={entry.scope_version or 'none'}")
        if not clear:
            if selected:
                typer.echo(f"{len(selected)} entry(ies) selected; re-run with --clear to remove")
            return
        for k in selected:
            del ledger[k]
        write_reject_ledger(path, ledger)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"cleared {len(selected)} entry(ies) from {path}; next sweep re-classifies them")


def _read_json_list(path: Path, *, label: str) -> list[object]:
    """Read a JSON-list staging file (candidates/verdicts) or raise a labelled ConfigError."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError(f"{label} must be a JSON list, got {type(raw).__name__}")
    return list(raw)  # pyright: ignore[reportUnknownArgumentType]


@app.command(name="apply-verdicts")
def apply_verdicts(
    input_file: Annotated[Path, typer.Option("--in", help="candidates.json to split.")],
    verdicts_file: Annotated[
        Path, typer.Option("--verdicts", help="verdicts.json from the classifier.")
    ],
    out: Annotated[
        Path | None,
        typer.Option(help="Output dir for classified.json + rejects.json (default: --in's dir)."),
    ] = None,
) -> None:
    """Split staged candidates into classified (in-scope, topics applied) + rejects.

    The resumable classification step (backfill gap 1): the classifier subagent writes
    verdicts.json (``[{id, in_scope, topics, reason}]``); this applies them so a rate-limit or
    context cutoff only loses the unclassified tail (reported as 'pending'). Replaces the
    ad-hoc ``data/runs/build_*.py`` scripts.
    """
    try:
        candidates = [
            validate_model(Bill, item, label="candidate bill")
            for item in _read_json_list(input_file, label="candidates file")
        ]
        verdicts = [
            validate_model(Verdict, item, label="verdict")
            for item in _read_json_list(verdicts_file, label="verdicts file")
        ]
        classified, rejects, pending = split_by_verdict(candidates, verdicts)
        out_dir = out or input_file.parent
        classified_path = stage_json(
            [b.model_dump(mode="json") for b in classified],
            name="classified.json",
            out=out_dir,
        )
        stage_json(
            [b.model_dump(mode="json") for b in rejects], name="rejects.json", out=out_dir
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"applied {len(verdicts)} verdict(s): {len(classified)} in-scope,"
        f" {len(rejects)} reject(s), {len(pending)} pending -> {classified_path.parent}"
    )
    if pending:
        typer.echo(f"  pending (unclassified): {', '.join(pending)}")


def _read_summaries(path: Path) -> dict[str, str]:
    """Read a summaries.json ``{id: summary}`` object; non-object/non-str-value -> ConfigError."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read summaries file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"summaries file must be a JSON object, got {type(raw).__name__}")
    raw_dict: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    result: dict[str, str] = {}
    for key, value in raw_dict.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(value, str):
            raise ConfigError(
                f"summary for {str(key)!r} must be a string, got {type(value).__name__}"
            )
        result[str(key)] = value
    return result


@app.command(name="apply-summaries")
def apply_summaries_cmd(
    input_file: Annotated[Path, typer.Option("--in", help="classified.json to enrich in place.")],
    summaries_file: Annotated[
        Path, typer.Option("--summaries", help="summaries.json {id: summary} map.")
    ],
) -> None:
    """Merge a ``{id: summary}`` map into the classified bills, in place (backfill gap 2).

    The leaner summary handoff: a batch-summarizer subagent writes summaries.json; this sets
    each in-scope bill's plain-language summary, so a cutoff only loses the un-summarized tail
    (reported as 'pending'). render-classified then renders unchanged.

    The rewrite is in place and non-atomic; if it is interrupted, regenerate classified.json by
    re-running ``apply-verdicts`` (candidates.json and verdicts.json are still present), then
    re-apply.
    """
    try:
        classified = [
            validate_model(Bill, item, label="classified bill")
            for item in _read_json_list(input_file, label="classified file")
        ]
        summaries = _read_summaries(summaries_file)
        updated, pending = apply_summaries(classified, summaries)
        stage_json(
            [b.model_dump(mode="json") for b in updated],
            name=input_file.name,
            out=input_file.parent,
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"applied {len(summaries)} summary(ies): {len(updated) - len(pending)} set,"
        f" {len(pending)} pending"
    )
    if pending:
        typer.echo(f"  pending (un-summarized): {', '.join(pending)}")


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
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop already-tracked and cached-reject bills (idempotent re-runs).",
        ),
    ] = False,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
) -> None:
    """Search a state via LegiScan and stage enriched candidate bills for classification.

    The deterministic first half of ``/zwiad-scan-states``: getSearchRaw recall →
    getBill enrich → ``candidates.json`` for the interactive classifier/summarizer
    subagents. The search query is the recall stage (D50), so no title pre-filter runs.

    ``--skip-existing`` drops bills already tracked in ``--wiki`` and bills cached in the
    reject ledger so a re-run does not re-stage them (D82). Defaults off.
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
        fetch_limit = limit * _STATE_OVERSAMPLE if skip_existing else limit
        candidates = source.discover(limit=fetch_limit)
        if skip_existing:
            known = _existing_state_bill_ids(wiki, state)
            ledger = load_reject_ledger(wiki / ".rejects" / "state.json")
            before = len(candidates)
            candidates = filter_by_key(candidates, known, key_of=state_key)
            after_unseen = len(candidates)
            candidates = filter_cached_rejects(
                candidates, ledger, key_of=state_key, cursor_of=state_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(candidates)} cached-reject of {before} scanned"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        candidates = candidates[:limit]
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} {state} candidate(s) to {path}")


@app.command(name="fetch-state-enacted-candidates")
def fetch_state_enacted_candidates(
    state: Annotated[str, typer.Option(help="Two-letter state, e.g. ca.")],
    year: Annotated[int, typer.Option(help="Target year; resolves to the session(s) covering it.")],
    # Default high (vs fetch_state_candidates's 5): backfill enumerates most of a
    # session's enacted laws, not just a handful of newest search hits.
    limit: Annotated[
        int, typer.Option(min=1, help="Max in-scope candidates to stage (recall output cap).")
    ] = 250,
    classify_all: Annotated[
        bool,
        typer.Option(
            "--classify-all/--no-classify-all",
            help="Skip the recall pre-filter; stage every enacted bill for classification.",
        ),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop bills already tracked or in the state reject ledger.",
        ),
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
) -> None:
    """Fetch a state session's ENACTED bills and stage the in-scope ones for classification.

    Enacted-first discovery half of ``/zwiad-backfill-enacted-state`` (D84): ``getSessionList``
    resolves ``--year`` to the session(s) covering it, then ``getMasterList`` lists that
    session's bills and we keep only ``status == 4 (Passed)`` — non-enacted bills never enter
    the pipeline. By default a free title+description keyword recall keeps the topically-
    relevant enacted bills and the classifier subagent gates the survivors; ``--classify-all``
    skips recall and stages every enacted bill.
    """
    try:
        api_key = load_settings().require_legiscan_api_key()
        source = LegiScanSource(api_key, state)
        sessions = [s for s in source.list_sessions() if s.year_start <= year <= s.year_end]
        if not sessions:
            raise ConfigError(f"no {state} session covers year {year}")
        # Dedup across sessions by native_id (preserving order): a special session can
        # overlap a regular session's year span, so --year may match >1 session and
        # surface the same bill twice — staging it once avoids a double enrich.
        enacted: list[Candidate] = []
        seen_ids: set[str] = set()
        for session in sessions:
            for cand in source.list_session_enacted(session.session_id):
                if cand.native_id in seen_ids:
                    continue
                seen_ids.add(cand.native_id)
                enacted.append(cand)
        if classify_all:
            candidates = enacted
        else:
            seeds = load_reference(topics).seeds
            candidates = keyword_filter(enacted, seeds)
        if skip_existing:
            known = _existing_state_bill_ids(wiki, state)
            ledger = load_reject_ledger(wiki / ".rejects" / "state.json")
            before = len(candidates)
            candidates = filter_by_key(candidates, known, key_of=state_key)
            after_unseen = len(candidates)
            candidates = filter_cached_rejects(
                candidates, ledger, key_of=state_key, cursor_of=state_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(candidates)} cached-reject of {before} enacted"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        candidates = candidates[:limit]
        bills = [enrich(source, candidate) for candidate in candidates]
        bills = dedupe_companions(bills)  # D93: collapse same-as Assembly/Senate pairs
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} enacted {state} candidate(s) to {path}")


@app.command(name="fetch-bill")
def fetch_bill(
    bill: Annotated[
        str,
        typer.Option(help="Bill ref: '118/hr/2670' (federal) or a LegiScan bill_id with --state."),
    ],
    state: Annotated[
        str | None,
        typer.Option(help="Two-letter state for LegiScan, e.g. ca. Omit for a federal bill."),
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Run directory for classified.json.")] = None,
) -> None:
    """Fetch one bill by id into a one-item ``classified.json`` for ``extract-text``.

    Re-derives a fully-enriched ``Bill`` from its source — LegiScan when ``--state``
    is given, else Congress.gov — and stages it as the single-item JSON list that
    ``extract-text`` consumes, so an already-committed wiki page can have its
    official text downloaded and converted.
    """
    try:
        settings = load_settings()
        source: LegiScanSource | CongressSource = (
            LegiScanSource(settings.require_legiscan_api_key(), state)
            if state
            else CongressSource(settings.require_congress_api_key())
        )
        fetched = source.fetch(bill)
        path = stage_json([fetched.model_dump(mode="json")], name="classified.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {fetched.id} to {path}")


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


@app.command(name="fetch-state-leg-history")
def fetch_state_leg_history(
    bill: Annotated[str, typer.Option(help="LegiScan bill_id, e.g. 1904800 (CA SB-53).")],
    state: Annotated[str, typer.Option(help="Two-letter state, e.g. ca.")],
    out: Annotated[
        Path | None, typer.Option(help="Run directory for leghistory.json.")
    ] = None,
) -> None:
    """Fetch an enacted STATE bill and stage its legislative-history inputs (PHASE-16 / D75).

    Assembles the state spine (text versions, roll-call votes, enactment) and research leads
    (supplements as Tier-2 media) from a SINGLE LegiScan getBill, writing them to
    ``leghistory.json`` for the interactive session's researcher/verifier subagents — feeding
    the same downstream (build-verifier-input -> verifier -> assemble-leg-history-input ->
    render-leg-history) the federal flow uses. There is no GovInfo for states, so committee
    reports / floor / hearings are left for the researcher.
    """
    try:
        settings = load_settings()
        source = LegiScanSource(settings.require_legiscan_api_key(), state)
        inputs = source.fetch_leg_history(bill)
        fetched = inputs.bill
        if not fetched.enacted:
            raise ConfigError(
                f"bill {fetched.id} is not enacted — legislative history is assembled"
                " only for enacted bills"
            )
        spine = assemble_state_spine(
            fetched, inputs.votes, committee_reports=inputs.committee_analyses
        )
        leads = collect_state_leads(fetched, inputs.supplement_media)
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


# A browser-like User-Agent for the deterministic grounding fetch. Some legislative
# WAFs (e.g. gov.ca.gov) 403 the default "python-httpx/x" agent, which fail-closed
# dropped a verifier-confirmed signing statement in the PHASE-16 UAT (PHASE-17 / D76).
_GATE_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
}


def _is_pdf_response(resp: httpx.Response) -> bool:
    """True when *resp* is a PDF — by content-type or the ``%PDF-`` magic bytes.

    The magic-byte fallback catches servers that label a PDF as a generic
    ``application/octet-stream``.
    """
    if "application/pdf" in resp.headers.get("content-type", "").lower():
        return True
    return resp.content[:5] == b"%PDF-"


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from PDF *data* via the Docling boundary; ``""`` when unavailable.

    Deterministic (no LLM) and never raises: the grounding gate must never crash a
    render, so an absent Docling (D68, optional) or any extraction failure yields ``""``
    and the gate fail-closed drops the item (quote-not-found), exactly as it would for an
    unfetchable page. Docling parses a document path, so the already-fetched bytes are
    written to a temp file that is always removed.
    """
    if not docling_available():
        return ""
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(data)
            tmp_path = Path(fh.name)
        return extract_markdown(tmp_path)
    except Exception:  # noqa: BLE001 — gate must never raise; any failure -> fail-closed drop
        return ""
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _fetch_url(url: str) -> tuple[int, str]:
    """Fetch a URL for grounding; returns (status_code, body_text).

    Sends a browser-like User-Agent (so UA-gated hosts return 200, PHASE-17) and, for a
    200 PDF response, returns Docling-extracted text so PDF-sourced quotes can ground.
    Body-text extraction is deterministic (no LLM), preserving the gate's trust boundary.
    Never raises — returns (0, '') on any HTTP error or on a malformed researcher-supplied
    URL (``httpx.InvalidURL``, which is NOT an HTTPError subclass and would otherwise crash
    the whole render).
    """
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True, headers=_GATE_HEADERS)
    except (httpx.HTTPError, httpx.InvalidURL):
        return (0, "")
    if resp.status_code == 200 and _is_pdf_response(resp):
        return (200, _extract_pdf_text(resp.content))
    return (resp.status_code, resp.text)


def _load_leghistory(run_dir: Path) -> dict[str, object]:
    """Read ``<run_dir>/leghistory.json`` (bill + spine + leads) or raise ConfigError.

    Required by both PHASE-15 steps: it carries the ``bill`` (for the verifier subject and
    the render-input) and the ``spine`` (for the render-input).
    """
    path = run_dir / "leghistory.json"
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a JSON object, got {type(raw).__name__}")
    payload: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    return payload


def _load_lane_payloads(run_dir: Path) -> dict[str, object | None]:
    """Load ``lane-<name>.json`` for each lane; ``None`` when missing or invalid JSON.

    A ``None`` lane is treated by :func:`merge_lanes` as a dropped lane — mirroring the
    orchestrator's "retry once, then drop just that lane" rule.  Both PHASE-15 steps load the
    lanes the same way so the two merges see identical inputs.
    """
    lanes: dict[str, object | None] = {}
    for lane in LANE_ORDER:
        path = run_dir / f"lane-{lane}.json"
        try:
            lanes[lane] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lanes[lane] = None
    return lanes


@app.command(name="build-verifier-input")
def build_verifier_input(
    run_dir: Annotated[
        Path, typer.Option("--run-dir", help="Run dir with leghistory.json + lane-*.json.")
    ],
) -> None:
    """Merge the researcher lanes and stage the verifier input (PHASE-15 step 1 / D74).

    Reads ``leghistory.json`` (for the bill) and the four ``lane-<name>.json`` files, runs the
    deterministic :func:`merge_lanes`, and writes ``verifier-input.json`` — a ``subject`` block
    plus index-stamped ``statements`` / ``related_media``.  The interactive session dispatches
    the leg-history-verifier over that file, then runs ``assemble-leg-history-input``.  Pure
    deterministic plumbing: NO LLM calls.
    """
    try:
        leghistory = _load_leghistory(run_dir)
        if "bill" not in leghistory:
            raise ConfigError("leghistory.json is missing required key 'bill'")
        bill = validate_model(Bill, leghistory["bill"], label="bill")

        merged = merge_lanes(_load_lane_payloads(run_dir))

        verifier_input = {
            "subject": {
                "citation": bill.bill_number,
                "title": bill.title,
                "topics": bill.topics,
                "sponsors": bill.sponsors,
            },
            "statements": [
                {
                    "index": i,
                    "speaker": s.speaker,
                    "quote": s.quote,
                    "source_url": s.source_url,
                    "relation": s.relation,
                }
                for i, s in enumerate(merged.statements)
            ],
            "related_media": [
                {
                    "index": i,
                    "title": m.title,
                    "url": m.url,
                    "kind": m.kind,
                    "relation": m.relation,
                }
                for i, m in enumerate(merged.related_media)
            ],
        }
        path = stage_json(verifier_input, name="verifier-input.json", out=run_dir)

        typer.echo(
            f"verifier-input: {len(merged.statements)} statement(s),"
            f" {len(merged.related_media)} media,"
            f" {len(merged.dropped_lanes)} lane(s) dropped -> {path}"
        )
        for lane in merged.dropped_lanes:
            typer.echo(f"  dropped lane: {lane}")
        for ident, reason in merged.parse_dropped:
            typer.echo(f"  parse-drop: {ident} — {reason}")
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _load_run_json_object(path: Path) -> dict[str, object]:
    """Read a required run-dir JSON object (e.g. verifier.json) or raise ConfigError."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a JSON object, got {type(raw).__name__}")
    payload: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    return payload


def _verdicts_by_index(
    raw_verdicts: object, *, label: str
) -> tuple[dict[int, dict[str, object]], list[tuple[str, str]]]:
    """Index verifier verdict entries by their self-reported ``index``.

    Skips (with an audit note) any entry that is not an object or whose ``index`` is not an
    integer — an unparseable verdict cannot confirm anything, so the item it would have
    scored falls through to verified:false (fail-closed) rather than aborting the assemble.
    """
    by_index: dict[int, dict[str, object]] = {}
    audit: list[tuple[str, str]] = []
    for v in _as_list(raw_verdicts, label):
        if not isinstance(v, dict):
            audit.append((label, "verdict entry is not an object"))
            continue
        entry: dict[str, object] = v  # pyright: ignore[reportUnknownVariableType]
        idx = entry.get("index")
        if not isinstance(idx, int):
            audit.append((label, f"verdict 'index' is not an integer: {idx!r}"))
            continue
        by_index[idx] = entry
    return by_index, audit


def _str_field(entry: dict[str, object], key: str) -> str:
    """Return entry[key] when it is a string, else ``""`` (verdict echoes are optional)."""
    value = entry.get(key)
    return value if isinstance(value, str) else ""


def _attach_statement_verdicts(
    statements: tuple[Statement, ...], raw_verdicts: object
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    """Build the render-input ``verdicts`` array — one per merged statement, echo-validated.

    Each emitted verdict is keyed by the statement's MERGED index.  The verifier echo
    (speaker + quote_prefix) is cross-checked against the merged statement; a verified verdict
    whose echo does not match is downgraded to verified:false (fail-closed) — the same
    discipline render-leg-history enforces (kept here as defense in depth, D74).  A merged
    statement with no verdict gets an explicit verified:false entry.
    """
    by_index, audit = _verdicts_by_index(raw_verdicts, label="verifier statements")
    out: list[dict[str, object]] = []
    for i, stmt in enumerate(statements):
        entry = by_index.get(i)
        if entry is None:
            audit.append((f"statement[{i}] {stmt.speaker}", "no verifier verdict"))
            out.append(
                {
                    "index": i,
                    "speaker": "",
                    "quote_prefix": "",
                    "verified": False,
                    "note": "no verifier verdict for this statement",
                }
            )
            continue
        echo_speaker = _str_field(entry, "speaker")
        echo_prefix = _str_field(entry, "quote_prefix")
        verified = bool(entry.get("verified"))
        if verified:
            speaker_ok = echo_speaker == stmt.speaker
            prefix_ok = bool(echo_prefix) and stmt.quote.startswith(echo_prefix)
            if not (speaker_ok and prefix_ok):
                verified = False
                audit.append(
                    (
                        f"statement[{i}] {stmt.speaker}",
                        "verifier echo mismatch (downgraded to false)",
                    )
                )
        out.append(
            {
                "index": i,
                "speaker": echo_speaker,
                "quote_prefix": echo_prefix,
                "verified": verified,
                "note": _str_field(entry, "note"),
            }
        )
    for idx in by_index:
        if idx >= len(statements):
            audit.append(
                ("verifier statements", f"orphan verdict index {idx} (no such merged statement)")
            )
    return out, audit


def _attach_media_verdicts(
    related_media: tuple[RelatedMedia, ...], raw_verdicts: object
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    """Build the render-input ``media_verdicts`` array — one per merged media item, echo-validated.

    Mirrors :func:`_attach_statement_verdicts` with the Tier-2 ``title_prefix`` echo: a verified
    verdict whose echoed title does not prefix the merged media title is downgraded fail-closed.
    """
    by_index, audit = _verdicts_by_index(raw_verdicts, label="verifier related_media")
    out: list[dict[str, object]] = []
    for i, media in enumerate(related_media):
        entry = by_index.get(i)
        if entry is None:
            audit.append((f"related_media[{i}] {media.title}", "no verifier verdict"))
            out.append(
                {
                    "index": i,
                    "title_prefix": "",
                    "verified": False,
                    "note": "no verifier verdict for this media",
                }
            )
            continue
        echo_title = _str_field(entry, "title_prefix")
        verified = bool(entry.get("verified"))
        if verified and not (echo_title and media.title.startswith(echo_title)):
            verified = False
            audit.append(
                (
                    f"related_media[{i}] {media.title}",
                    "verifier echo mismatch (downgraded to false)",
                )
            )
        out.append(
            {
                "index": i,
                "title_prefix": echo_title,
                "verified": verified,
                "note": _str_field(entry, "note"),
            }
        )
    for idx in by_index:
        if idx >= len(related_media):
            audit.append(
                ("verifier related_media", f"orphan verdict index {idx} (no such merged media)")
            )
    return out, audit


@app.command(name="assemble-leg-history-input")
def assemble_leg_history_input(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Run dir with leghistory.json, lane-*.json, verifier.json."),
    ],
) -> None:
    """Attach verifier verdicts to the merged research; stage the render input (PHASE-15 / D74).

    Re-runs the deterministic :func:`merge_lanes` (byte-identical to ``build-verifier-input``'s,
    so verdict indices align by construction), attaches each verifier verdict to its merged
    statement / media by index with the echo cross-check applied fail-closed, and writes
    ``leghistory-research.json`` — the staging file ``render-leg-history`` already consumes.
    Pure deterministic plumbing: NO LLM calls.
    """
    try:
        leghistory = _load_leghistory(run_dir)
        for key in ("bill", "spine"):
            if key not in leghistory:
                raise ConfigError(f"leghistory.json is missing required key '{key}'")

        merged = merge_lanes(_load_lane_payloads(run_dir))
        verifier = _load_run_json_object(run_dir / "verifier.json")

        verdicts, stmt_audit = _attach_statement_verdicts(
            merged.statements, verifier.get("statements")
        )
        media_verdicts, media_audit = _attach_media_verdicts(
            merged.related_media, verifier.get("related_media")
        )

        render_input = {
            "bill": leghistory["bill"],
            "spine": leghistory["spine"],
            "hearings": [h.model_dump(mode="json") for h in merged.hearings],
            "statements": [s.model_dump(mode="json") for s in merged.statements],
            "related_media": [m.model_dump(mode="json") for m in merged.related_media],
            "narrative": merged.narrative,
            "verdicts": verdicts,
            "media_verdicts": media_verdicts,
        }
        path = stage_json(render_input, name="leghistory-research.json", out=run_dir)

        verified_stmts = sum(1 for v in verdicts if v["verified"] is True)
        verified_media = sum(1 for v in media_verdicts if v["verified"] is True)
        typer.echo(
            f"render-input: {len(merged.statements)} statement(s)"
            f" ({verified_stmts} verifier-confirmed),"
            f" {len(merged.hearings)} hearing(s),"
            f" {len(merged.related_media)} media ({verified_media} confirmed),"
            f" narrative={'yes' if merged.narrative else 'no'} -> {path}"
        )
        for lane in merged.dropped_lanes:
            typer.echo(f"  dropped lane: {lane}")
        for ident, reason in (*merged.parse_dropped, *stmt_audit, *media_audit):
            typer.echo(f"  note: {ident} — {reason}")
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


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

        # Tier-2 related media (D69 Phase B): hearing/floor videos + reference pages, listed
        # WITHOUT a quote. Parsed per-item like statements/hearings; grounded by URL + an
        # independent verifier *identity* check (no verbatim-quote gate). Verdicts are keyed
        # by each media item's original index and carry a title_prefix echo that we cross-check
        # against the media at that index (fail-closed on mismatch — same discipline as
        # statements, mirroring the parse-drop index remap).
        parse_dropped_media: list[tuple[str, str]] = []
        related_media: list[RelatedMedia] = []
        media_original_indices: list[int] = []
        for i, item in enumerate(_as_list(payload.get("related_media"), "related_media")):
            try:
                related_media.append(RelatedMedia.model_validate(item))
                media_original_indices.append(i)
            except ValidationError as exc:
                parse_dropped_media.append((f"related_media[{i}]", str(exc)))

        media_verdicts_by_original: dict[int, tuple[bool, str]] = {}
        for v in _as_list(payload.get("media_verdicts"), "media_verdicts"):
            if not isinstance(v, dict):
                raise ConfigError("each entry in 'media_verdicts' must be a JSON object")
            mverdict: dict[str, object] = v  # pyright: ignore[reportUnknownVariableType]
            mindex = mverdict.get("index")
            if not isinstance(mindex, int):
                raise ConfigError(
                    f"media_verdict 'index' must be an integer, got {type(mindex).__name__}"
                )
            echo_title = mverdict.get("title_prefix")
            media_verdicts_by_original[mindex] = (
                bool(mverdict.get("verified")),
                echo_title if isinstance(echo_title, str) else "",
            )

        media_verifier_verdicts: dict[int, bool] = {}
        for new_pos, orig_idx in enumerate(media_original_indices):
            m_verified, echo_title = media_verdicts_by_original.get(orig_idx, (False, ""))
            if m_verified:
                media = related_media[new_pos]
                if not (echo_title and media.title.startswith(echo_title)):
                    m_verified = False
            media_verifier_verdicts[new_pos] = m_verified

        # A single transcript-aware fetch for BOTH gates: a YouTube source_url resolves to its
        # caption text (D72 fallback); every other URL uses the normal HTTP fetch. The gate
        # logic (ground_items / ground_related) is unchanged — it just receives caption text
        # for a video source_url. `_fetch_url` is referenced by name so tests can monkeypatch it.
        # PHASE-20: a run-scoped memo wraps it so each distinct url is fetched once across the
        # statement / hearing / media gates AND the PHASE-19 render retry's static re-fetches.
        gate_fetch = memoize_fetch(make_gate_fetch(_fetch_url))

        result = ground_items(
            statements, hearings, fetch=gate_fetch, verifier_verdicts=verifier_verdicts
        )

        # PHASE-19 (Fix 3): second pass re-grounds statements that dropped as
        # "quote not found" by rendering ONLY those urls through headless Chromium (the
        # JS-injected-quote signature). Optional/fail-closed: skipped entirely when
        # Playwright is absent, so behaviour is identical to the static gate without it.
        # Re-runs the FULL gate with the ORIGINAL verdicts, so verdict-by-index keying is
        # preserved (no subset to re-key — the highest-stakes failure mode).
        js_recovered = 0
        if playwright_available():
            result, js_recovered = reground_with_render(
                statements,
                hearings,
                result,
                static_fetch=gate_fetch,
                render_html=render_page_html,
                verifier_verdicts=verifier_verdicts,
            )

        media_result = ground_related(
            related_media, fetch=gate_fetch, verifier_verdicts=media_verifier_verdicts
        )

        # Collapse near-duplicate statements that BOTH grounded (e.g. a press-lane
        # "Gavin Newsom" and a signing-lane "Gov. Gavin Newsom" with the same quote).
        # Done POST-grounding so a groundable copy is never dropped for an ungroundable
        # near-dup (merge dedup is first-wins by lane order, so it cannot do this safely).
        grounded_statements = dedup_statements(result.statements)
        stmt_near_dup_drops = len(result.statements) - len(grounded_statements)

        final = spine.model_copy(
            update={
                "hearings": list(result.hearings),
                "statements": grounded_statements,
                "related_media": list(media_result.media),
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
        stmt_grounded = len(grounded_statements)
        # Gate ground-drops are measured against the pre-dedup grounded set; near-dup
        # collapses are reported separately so the reconciliation stays exact.
        stmt_ground_drops = len(statements) - len(result.statements)
        stmt_input = (
            stmt_grounded + stmt_near_dup_drops + stmt_ground_drops + stmt_parse_drops
        )

        hearing_parse_drops = len(parse_dropped_hearings)
        hearing_kept = len(result.hearings)
        hearing_ground_drops = len(hearings) - hearing_kept
        hearing_input = hearing_kept + hearing_ground_drops + hearing_parse_drops

        media_parse_drops = len(parse_dropped_media)
        media_kept = len(media_result.media)
        media_ground_drops = len(related_media) - media_kept
        media_input = media_kept + media_ground_drops + media_parse_drops

        page_status = "written" if written else "unchanged"
        typer.echo(
            f"{bill.id}: {spine_summary} | "
            f"statements: {stmt_input} input / {stmt_grounded} grounded"
            f" / {stmt_parse_drops} parse-drop / {stmt_ground_drops} ground-drop"
            f" / {stmt_near_dup_drops} near-dup / {js_recovered} js-recovered | "
            f"hearings: {hearing_input} input / {hearing_kept} grounded"
            f" / {hearing_parse_drops} parse-drop / {hearing_ground_drops} ground-drop | "
            f"media: {media_input} input / {media_kept} grounded"
            f" / {media_parse_drops} parse-drop / {media_ground_drops} ground-drop | "
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
        for identifier, reason in parse_dropped_media:
            typer.echo(f"  dropped related_media: {identifier} — {reason}")
        for d in result.dropped:
            typer.echo(f"  dropped {d.kind}: {d.identifier} — {d.reason}")
        for d in media_result.dropped:
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


@app.command(name="extract-text")
def extract_text(
    input_file: Annotated[
        Path, typer.Option("--in", help="classified.json (Bill/EnforcementAction dumps).")
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root holding the pages + sidecars.")] = Path(
        "wiki"
    ),
    limit: Annotated[
        int | None, typer.Option(min=1, help="Max items to extract this run.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List planned extractions; write nothing.")
    ] = False,
) -> None:
    """Extract operative source documents to ``<id>.text.md`` sidecars via Docling.

    For each tracked page it picks the operative document — a bill's
    enrolled/latest text version, or an enforcement action's press release plus
    linked filing PDFs — extracts Markdown through the Docling boundary, writes the
    sidecar, and links it from the page. The existing "Full Text" source links are
    left untouched. Per-item isolation: a malformed or unfetchable item is recorded
    as a skip, never fatal (mirrors render-enforcement).
    """
    try:
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read classified file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"classified file must be a JSON list, got {type(raw).__name__}")
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    # Fail fast (real runs only): Docling is an optional, unlocked extra. Dry-run
    # never invokes it, so it stays useful for previewing without Docling installed.
    if not dry_run and not docling_available():
        typer.echo(
            "error: Docling is not installed. Install it to run extract-text:\n"
            "  uv pip install docling\n"
            "then re-run with `uv run --no-sync zwiadbrain extract-text ...`.\n"
            "(Use --dry-run to preview planned extractions without Docling.)",
            err=True,
        )
        raise typer.Exit(1)
    if limit is not None:
        entries = entries[:limit]

    done = 0
    dropped: list[tuple[str, str]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            dropped.append((f"entry[{i}]", "entry is not a JSON object"))
            continue
        record: dict[str, object] = entry  # pyright: ignore[reportUnknownVariableType]
        identifier = str(record.get("id") or f"entry[{i}]")
        try:
            item: Bill | EnforcementAction
            if record.get("type") == "enforcement":
                item = validate_model(EnforcementAction, record, label="enforcement item")
            else:
                item = validate_model(Bill, record, label="bill item")
            if dry_run:
                plan = plan_extraction(item, wiki)
                if plan is None:
                    dropped.append((identifier, "no committed page or no fetchable document"))
                    continue
                sidecar, urls = plan
                typer.echo(f"would extract {identifier}: {len(urls)} doc(s) -> {sidecar}")
                done += 1
                continue
            sidecar_written = extract_item(item, wiki)
            if sidecar_written is None:
                dropped.append((identifier, "no committed page or no fetchable document"))
                continue
            done += 1
        except Exception as exc:  # noqa: BLE001 - per-item isolation: one bad item never aborts the batch
            dropped.append((identifier, str(exc)))

    verb = "would extract" if dry_run else "extracted"
    typer.echo(f"extract-text: {verb} {done} item(s), {len(dropped)} skipped")
    for ident, reason in dropped:
        typer.echo(f"  - skipped {ident}: {reason}", err=True)


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
