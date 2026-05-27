"""Tests for the ZwiadBrain CLI entrypoint.

The full command set is added per phase; for now we only pin that the app is
wired up and reports its version.
"""

from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain import __version__
from zwiadbrain.cli import app
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.render import write_page

runner = CliRunner()


def test_version_command_prints_package_version() -> None:
    """should print the package version"""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_reindex_command_reports_indexed_count(tmp_path: Path) -> None:
    """should rebuild the index from a wiki root and report how many pages it indexed"""
    wiki = tmp_path / "wiki"
    write_page(Bill(id="hr-1", jurisdiction="US", title="A bill", bill_number="HR 1"), wiki)
    result = runner.invoke(
        app, ["reindex", "--wiki", str(wiki), "--db", str(tmp_path / "i.sqlite")]
    )
    assert result.exit_code == 0
    assert "1" in result.stdout
