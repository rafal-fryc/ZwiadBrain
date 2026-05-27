"""ZwiadBrain command-line interface.

Commands are added per phase (scan, backfill, render, reindex, sync-lawbrain,
review, lawbrain-status). For now the app only reports its version.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Annotated

import typer

from zwiadbrain import __version__
from zwiadbrain.config import load_settings
from zwiadbrain.exceptions import AppError, ConfigError
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.discover import keyword_filter, recall_filter
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.reference.loader import load_reference
from zwiadbrain.sources.congress import CongressSource
from zwiadbrain.store import Store

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

    A callback is present so the app stays a multi-command group (commands keep
    their names) even while only ``version`` is wired up.
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
        run_dir = out or Path("data/runs") / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "candidates.json"
        payload = [bill.model_dump(mode="json") for bill in bills]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
        raw = json.loads(input_file.read_text(encoding="utf-8"))
        bills = [Bill.model_validate(item) for item in raw]
        for bill in bills:
            unknown = [topic for topic in bill.topics if topic not in topic_keys]
            if unknown:
                raise ConfigError(f"bill {bill.id} has unknown topic(s): {', '.join(unknown)}")
        written = sum(write_page(bill, wiki) for bill in bills)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"rendered {written} page(s) into {wiki}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
