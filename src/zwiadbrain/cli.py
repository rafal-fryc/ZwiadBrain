"""ZwiadBrain command-line interface.

These are the deterministic fetch/render halves that the interactive Claude Code
slash commands drive (the subagents run between a fetch and a render; Python
makes no LLM calls — DECISIONS.md D26/D27). Commands:

- ``version`` / ``reindex`` — utilities.
- ``backfill`` — deterministic discover→enrich→render (no classification).
- ``fetch-candidates`` / ``render-classified`` — the ``/zwiad-backfill`` halves.
- ``fetch-leg-history`` / ``render-leg-history`` — the ``/zwiad-leg-history`` halves.
- ``fetch-refreshable`` / ``render-refreshed`` — the ``/zwiad-refresh`` halves.

State sources, enforcement, and law-brain commands are not yet implemented; see
``ARCHITECTURE.md``.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError

from zwiadbrain import __version__
from zwiadbrain.config import load_settings
from zwiadbrain.exceptions import AppError, ConfigError, WikiSchemaError
from zwiadbrain.models import Bill, Hearing, LegHistory, Statement
from zwiadbrain.pipeline.discover import keyword_filter, recall_filter
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.pipeline.ids import parse_bill_id
from zwiadbrain.pipeline.leg_history import assemble_spine, collect_leads, ground_items
from zwiadbrain.pipeline.refresh import (
    apply_classifier_flip,
    detect_refreshable,
    preserve_leg_history,
    summary_hash,
)
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.pipeline.staging import stage_json, validate_model
from zwiadbrain.reference.loader import load_reference
from zwiadbrain.sources.congress import CongressSource
from zwiadbrain.sources.govinfo import GovInfoSource
from zwiadbrain.store import Store
from zwiadbrain.wiki.schema import from_page

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
    with Store(db) as store:
        count = store.reindex(wiki)
    typer.echo(f"reindexed {count} pages from {wiki}")


@app.command()
def backfill(
    congress: Annotated[int, typer.Option(help="Congress number, e.g. 118.")],
    limit: Annotated[int, typer.Option(help="Max bills to enrich and render.")] = 5,
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    seed: Annotated[
        list[str] | None, typer.Option(help="Keyword seed for recall filtering (repeatable).")
    ] = None,
) -> None:
    """Enrich and render federal bills from a Congress into the wiki."""
    try:
        api_key = load_settings().require_congress_api_key()
        source = CongressSource(api_key)
        candidates = source.discover(congress=congress, limit=limit * 5 if seed else limit)
        candidates = keyword_filter(candidates, seed)[:limit]
        written = sum(write_page(enrich(source, candidate), wiki) for candidate in candidates)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"backfilled {written} federal bill(s) into {wiki}")


@app.command(name="fetch-candidates")
def fetch_candidates(
    congress: Annotated[int, typer.Option(help="Congress number, e.g. 118.")],
    limit: Annotated[int, typer.Option(help="Max candidates to fetch.")] = 5,
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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
