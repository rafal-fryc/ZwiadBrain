"""ZwiadBrain command-line interface.

Commands are added per phase (scan, backfill, render, reindex, sync-lawbrain,
review, lawbrain-status). For now the app only reports its version.
"""

from pathlib import Path
from typing import Annotated

import typer

from zwiadbrain import __version__
from zwiadbrain.config import load_settings
from zwiadbrain.exceptions import AppError
from zwiadbrain.pipeline.discover import keyword_filter
from zwiadbrain.pipeline.enrich import enrich
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.sources.congress import CongressSource
from zwiadbrain.store import Store

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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
