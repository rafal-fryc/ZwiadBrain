"""Tests for the ZwiadBrain CLI entrypoint.

The full command set is added per phase; for now we only pin that the app is
wired up and reports its version.
"""

from typer.testing import CliRunner

from zwiadbrain import __version__
from zwiadbrain.cli import app

runner = CliRunner()


def test_version_command_prints_package_version() -> None:
    """should print the package version"""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
