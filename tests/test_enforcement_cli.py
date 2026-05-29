import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import EnforcementAction, EnforcementDevelopment
from zwiadbrain.pipeline.render import write_page

runner = CliRunner()
_FIX = Path(__file__).parent / "fixtures" / "enforcement"

_GLOBEX_HTML = "<html><body><main>Docket No. C-4790 order.</main></body></html>"


@respx.mock
def test_fetch_enforcement_candidates_stages_candidates_and_matters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rss = "https://www.ftc.gov/feeds/press-release.xml"
    respx.get(rss).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/01/acme").mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press.html").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/03/globex").mock(
        return_value=httpx.Response(200, text=_GLOBEX_HTML))

    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text("[enforcement]\nenabled = true\n[enforcement.ftc]\n"
                    f'rss_url = "{rss}"\nenabled = true\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wiki" / "federal" / "enforcement").mkdir(parents=True)

    out = tmp_path / "run"
    result = runner.invoke(app, ["fetch-enforcement-candidates", "--agency", "ftc",
                                 "--limit", "10", "--lookback-days", "100000", "--out", str(out)])
    assert result.exit_code == 0, result.output
    candidates = json.loads((out / "candidates.json").read_text())
    matters = json.loads((out / "matters.json").read_text())
    assert matters == []  # no existing enforcement pages yet
    globex = next(c for c in candidates if "Globex" in c["title"])
    assert globex["strong_key"] == "c-4790"
    assert globex["text"] and "C-4790" in globex["text"]


@respx.mock
def test_fetch_enforcement_candidates_links_existing_matter_by_strong_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rss = "https://www.ftc.gov/feeds/press-release.xml"
    respx.get(rss).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/01/acme").mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press.html").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/03/globex").mock(
        return_value=httpx.Response(200, text=_GLOBEX_HTML))

    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text("[enforcement]\nenabled = true\n[enforcement.ftc]\n"
                    f'rss_url = "{rss}"\nenabled = true\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # An existing tracked matter with docket c-4790 — render it so from_page reads it back.
    action = EnforcementAction(
        id="ftc-c-4790",
        jurisdiction="US",
        title="FTC v. Globex",
        agency="FTC",
        docket="c-4790",
        topics=["ai"],
        developments=[
            EnforcementDevelopment(
                date=dt.date(2025, 3, 3),
                summary="Final order entered.",
                source_url="https://www.ftc.gov/news/press-releases/2025/03/globex",
            )
        ],
    )
    write_page(action, tmp_path / "wiki")

    out = tmp_path / "run"
    result = runner.invoke(app, ["fetch-enforcement-candidates", "--agency", "ftc",
                                 "--limit", "10", "--lookback-days", "100000", "--out", str(out)])
    assert result.exit_code == 0, result.output

    matters = json.loads((out / "matters.json").read_text())
    assert len(matters) == 1
    assert matters[0]["id"] == "ftc-c-4790"
    assert matters[0]["agency_slug"] == "ftc"  # proves the config-derived jurisdiction map

    candidates = json.loads((out / "candidates.json").read_text())
    globex = next(c for c in candidates if "Globex" in c["title"])
    assert globex["matter_id"] == "ftc-c-4790"
    assert globex["match_source"] == "strong_key"
