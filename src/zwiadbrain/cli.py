"""ZwiadBrain command-line interface.

Commands are added per phase (scan, backfill, render, reindex, sync-lawbrain,
review, lawbrain-status). For now the app only reports its version.
"""

import typer

from zwiadbrain import __version__

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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
