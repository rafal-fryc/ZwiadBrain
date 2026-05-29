import json
from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import EnforcementAction
from zwiadbrain.wiki.schema import from_page

runner = CliRunner()


def _entry(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "matter_id": None, "match_source": "none", "match_confidence": 0.0,
        "agency": "FTC", "agency_slug": "ftc", "jurisdiction": "US",
        "strong_key": "c-4790", "respondent": "Acme, Inc.", "title": "FTC v. Acme",
        "topics": ["privacy"], "summary": "Data-security action.",
        "background": None, "allegations": "Failed to secure data.", "outcome": None,
        "significance": None, "action_type": "complaint", "statutes": ["FTC Act 5"],
        "penalties": None, "status": "filed", "date_filed": "2025-01-02",
        "date_resolved": None,
        "development": {"date": "2025-01-02", "summary": "Complaint filed.",
                        "source_url": "https://www.ftc.gov/a"},
        "source_url": "https://www.ftc.gov/a", "sources": {"FTC": "https://www.ftc.gov/a"},
    }
    base.update(over)
    return base


def test_render_enforcement_new_matter(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(tmp_path / "i.sqlite")])
    assert result.exit_code == 0, result.output
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    action = from_page(page.read_text(encoding="utf-8"))
    assert isinstance(action, EnforcementAction)
    assert action.id == "ftc-c-4790"
    assert action.developments[0].summary == "Complaint filed."


def test_render_enforcement_strong_key_consolidates(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    settle = _entry(matter_id="ftc-c-4790", match_source="strong_key", status="settled",
                    date_resolved="2025-06-01", penalties="$5M", outcome="Consent order.",
                    title="FTC Finalizes Order Against Acme",
                    development={"date": "2025-06-01", "summary": "Final order.",
                                 "source_url": "https://www.ftc.gov/b"},
                    source_url="https://www.ftc.gov/b", sources={"FTC": "https://www.ftc.gov/b"})
    (run / "classified.json").write_text(json.dumps([settle]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    action = from_page(page.read_text(encoding="utf-8"))
    assert isinstance(action, EnforcementAction)
    assert [d.summary for d in action.developments] == ["Complaint filed.", "Final order."]
    assert action.status == "settled" and action.penalties == "$5M"
    assert set(action.sources) == {"FTC"}


def test_render_enforcement_llm_match_failing_confirm_becomes_new_page(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry(
        matter_id=None, strong_key=None, respondent="Globex LLC", title="FTC v. Globex",
        development={"date": "2025-01-02", "summary": "Complaint.", "source_url": "https://x/g1"},
        source_url="https://x/g1", sources={"FTC": "https://x/g1"})]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    bad = _entry(matter_id="ftc-2025-globex", match_source="llm", match_confidence=0.9,
                 strong_key=None, respondent="Initech Inc.", title="FTC v. Initech",
                 date_filed="2025-02-01",
                 development={"date": "2025-02-01", "summary": "Complaint.",
                              "source_url": "https://x/i1"},
                 source_url="https://x/i1", sources={"FTC": "https://x/i1"})
    (run / "classified.json").write_text(json.dumps([bad]), encoding="utf-8")
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(db)])
    assert (wiki / "federal" / "enforcement" / "ftc-2025-initech.md").exists()
    assert "possible-duplicate" in result.output.lower()


def test_render_enforcement_idempotent(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    first = page.read_text(encoding="utf-8")
    again = _entry(matter_id="ftc-c-4790", match_source="strong_key")
    (run / "classified.json").write_text(json.dumps([again]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    assert page.read_text(encoding="utf-8") == first


def test_render_enforcement_consolidation_preserves_omitted_prose(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry(
        summary="Original summary.", allegations="Original allegations.")]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    # Consolidation item OMITS summary/allegations but adds a development + sets outcome.
    settle = _entry(matter_id="ftc-c-4790", match_source="strong_key", summary=None,
                    allegations=None, outcome="Settled.", status="settled",
                    development={"date": "2025-06-01", "summary": "Final order.",
                                 "source_url": "https://www.ftc.gov/b"},
                    source_url="https://www.ftc.gov/b", sources={"FTC": "https://www.ftc.gov/b"})
    (run / "classified.json").write_text(json.dumps([settle]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    action = from_page(page.read_text(encoding="utf-8"))
    assert isinstance(action, EnforcementAction)
    assert action.allegations == "Original allegations."
    assert action.summary == "Original summary."
    assert action.outcome == "Settled."
    assert len(action.developments) == 2


def test_render_enforcement_skips_entry_missing_development(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    valid = _entry()
    bad = _entry(strong_key="c-9999", title="FTC v. Beta")
    del bad["development"]  # malformed: missing required key
    (run / "classified.json").write_text(json.dumps([valid, bad]), encoding="utf-8")
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert (wiki / "federal" / "enforcement" / "ftc-c-4790.md").exists()
    assert not (wiki / "federal" / "enforcement" / "ftc-c-9999.md").exists()
    assert "dropped" in result.output.lower()


def test_render_enforcement_skips_entry_with_bad_development_url(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    db = tmp_path / "i.sqlite"
    run = tmp_path / "run"
    run.mkdir()
    valid = _entry()
    bad = _entry(strong_key="c-9999", title="FTC v. Beta",
                 development={"date": "2025-01-02", "summary": "Complaint.",
                             "source_url": "not-a-url"})
    (run / "classified.json").write_text(json.dumps([valid, bad]), encoding="utf-8")
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert (wiki / "federal" / "enforcement" / "ftc-c-4790.md").exists()
    assert not (wiki / "federal" / "enforcement" / "ftc-c-9999.md").exists()
    assert "dropped" in result.output.lower()
