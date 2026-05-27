"""ZwiadBrain command-line interface.

Commands are added per phase (scan, backfill, render, reindex, sync-lawbrain,
review, lawbrain-status). For now the app only reports its version.
"""

from pathlib import Path
from typing import Annotated

import typer

from zwiadbrain import __version__
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
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path(
        "data/cache/index.sqlite"
    ),
) -> None:
    """Rebuild the SQLite index/watchlist from committed wiki frontmatter."""
    with Store(db) as store:
        count = store.reindex(wiki)
    typer.echo(f"reindexed {count} pages from {wiki}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
