"""CLI tests for the law-brain fetch half (``fetch-lawbrain-candidates``)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import _summary_excerpt, app  # pyright: ignore[reportPrivateUsage]
from zwiadbrain.config import LawBrainSettings, Settings

_RUNNER = CliRunner()
_FIXTURE_LAWBRAIN = Path(__file__).parent / "fixtures" / "lawbrain"


def _settings(law_brain_path: Path | None, *, enabled: bool = True) -> Settings:
    """A Settings whose lawbrain block points at a (possibly missing) law brain."""
    lawbrain = LawBrainSettings(
        enabled=enabled,
        path=law_brain_path,
        commentary_only_slug_markers=["tracker", "landscape", "map", "scholarship"],
    )
    return Settings(lawbrain=lawbrain)


def _write_sb53_bill(wiki: Path) -> None:
    """Render a tracked CA SB 53 bill page so its key matches the law-brain page."""
    page = wiki / "bills" / "ca-2025-sb-53.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                "id: ca-2025-sb-53",
                "type: bill",
                "jurisdiction: US-CA",
                "title: Transparency in Frontier Artificial Intelligence Act",
                "bill_number: SB 53",
                "status: enrolled",
                "sources: {}",
                "commentary_sources: []",
                "---",
                "",
                "## Summary",
                "",
                "State frontier-AI transparency bill.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_enforcement(wiki: Path, *, id_: str, public_law: str = "Pub. L. 119-12") -> None:
    """Render a tracked enforcement page citing a public law (the cross-type key)."""
    page = wiki / "enforcement" / f"{id_}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                f"id: {id_}",
                "type: enforcement",
                "jurisdiction: US",
                f"title: United States v. {id_}",
                "agency: FTC",
                "statutes:",
                f"  - {public_law}",
                "sources: {}",
                "commentary_sources: []",
                "---",
                "",
                "## Background",
                "",
                "Fixture enforcement action.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_take_it_down_lawbrain_page(law_brain: Path) -> None:
    """A single-subject law-brain page whose citation yields the public-law key."""
    page = law_brain / "wiki" / "regulation-take-it-down-act.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                'title: "TAKE IT DOWN Act"',
                "type: regulation",
                "jurisdiction: US",
                "tags:",
                "  - ncii",
                "citation: \"Pub. L. 119-12\"",
                "status: active",
                "---",
                "",
                "## Summary",
                "",
                "Federal NCII statute enacted as Pub. L. 119-12.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_fetch_lawbrain_candidates_no_op_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — point lawbrain at a path with no wiki/ subdir (is_available() False).
    missing = tmp_path / "no-law-brain"
    missing.mkdir()
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(missing))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(app, ["fetch-lawbrain-candidates", "--out", str(out)])

    # Assert — exit 0, a no-op message, and no candidates file written.
    assert result.exit_code == 0, result.output
    assert "law brain unavailable" in result.output
    assert not (out / "lawbrain-candidates.json").exists()


def test_fetch_lawbrain_candidates_deterministic_match_and_marker_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a real fixture law brain + a tracked SB 53 bill sharing its key.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — staged both files; SB 53 is a deterministic link, tracker excluded.
    assert result.exit_code == 0, result.output
    candidates_path = out / "lawbrain-candidates.json"
    assert candidates_path.exists()
    assert (out / "targets.json").exists()

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    by_slug = {c["slug"]: c for c in candidates}

    assert "concept-state-ai-chatbot-tracker" not in by_slug  # fail-closed (D60)

    sb53 = by_slug["regulation-california-sb53-tfaia"]
    assert sb53["match"] == "deterministic"
    assert sb53["target_id"] == "ca-2025-sb-53"
    assert "US-CA::bill::SB-53" in sb53["keys"]
    assert sb53["shortlist"] is None

    targets = json.loads((out / "targets.json").read_text(encoding="utf-8"))
    assert {"id": "ca-2025-sb-53", "kind": "bill"}.items() <= {
        "id": targets[0]["id"],
        "kind": targets[0]["kind"],
    }.items()


def test_fetch_lawbrain_candidates_keyless_single_subject_gets_shortlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a single-subject law-brain page with no extractable key, plus a
    # same-jurisdiction tracked target the matcher could consider.
    law_brain = tmp_path / "law"
    (law_brain / "wiki").mkdir(parents=True)
    (law_brain / "wiki" / "concept-ai-liability-doctrine.md").write_text(
        "\n".join(
            [
                "---",
                'title: "AI Liability Doctrine"',
                "type: concept",
                "jurisdiction: US-CA",
                "tags:",
                "  - liability",
                "  - frontier-ai",
                "status: active",
                "---",
                "",
                "## Summary",
                "",
                "A single-subject doctrinal note with no bill, docket, or public-law key.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — keyless single-subject page gets a shortlist for the LLM matcher.
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    by_slug = {c["slug"]: c for c in candidates}
    entry = by_slug["concept-ai-liability-doctrine"]
    assert entry["match"] == "keyless"
    assert entry["target_id"] is None
    assert entry["keys"] == []
    # The same-jurisdiction (US-CA) SB 53 target appears in the shortlist.
    assert entry["shortlist"] == ["ca-2025-sb-53"]


def test_fetch_lawbrain_candidates_skips_settled_registry_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — record a link decision whose keys_hash matches the live key-set.
    from zwiadbrain.pipeline.lawbrain_keys import keys_hash, page_keys
    from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry
    from zwiadbrain.sources.lawbrain import LawBrainReader

    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    wiki.mkdir(parents=True, exist_ok=True)

    settings = _settings(law_brain)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: settings)

    effective_path = settings.effective_law_brain_path
    assert effective_path is not None
    reader = LawBrainReader(effective_path)
    sb53_page = next(
        p for p in reader.pages() if p.slug == "regulation-california-sb53-tfaia"
    )
    live_hash = keys_hash(
        page_keys(sb53_page, settings.lawbrain.commentary_only_slug_markers)
    )

    registry = LinkRegistry.load(wiki / "links.yaml")
    registry.record(
        LinkDecision(
            lawbrain_slug="regulation-california-sb53-tfaia",
            decision="link",
            target_id="ca-2025-sb-53",
            matched_by="deterministic",
            keys_hash=live_hash,
            decided=dt.date(2026, 5, 29),
        )
    )
    registry.dump(wiki / "links.yaml")
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — the settled page is skipped (keys_hash unchanged, D9).
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    slugs = {c["slug"] for c in candidates}
    assert "regulation-california-sb53-tfaia" not in slugs


def test_fetch_lawbrain_candidates_collision_when_two_targets_share_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — two tracked enforcement actions citing the same public law, and a
    # law-brain page whose citation yields that shared key -> a key collision.
    law_brain = tmp_path / "law"
    (law_brain / "wiki").mkdir(parents=True)
    _write_take_it_down_lawbrain_page(law_brain)
    wiki = tmp_path / "wiki"
    _write_enforcement(wiki, id_="ftc-acme")
    _write_enforcement(wiki, id_="ftc-beta")
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — the page collides on the shared key; both targets listed, no auto-link.
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    by_slug = {c["slug"]: c for c in candidates}
    entry = by_slug["regulation-take-it-down-act"]
    assert entry["match"] == "collision"
    assert entry["target_id"] is None
    assert entry["shortlist"] == ["ftc-acme", "ftc-beta"]
    assert "public_law::119-12" in entry["keys"]


def test_fetch_lawbrain_candidates_no_op_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an available law brain on disk, but lawbrain.enabled is False.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    monkeypatch.setattr(
        "zwiadbrain.cli.load_settings", lambda: _settings(law_brain, enabled=False)
    )
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(app, ["fetch-lawbrain-candidates", "--out", str(out)])

    # Assert — exit 0, no-op message, no candidates file (disabled guard, not error).
    assert result.exit_code == 0, result.output
    assert "law brain unavailable" in result.output
    assert not (out / "lawbrain-candidates.json").exists()


def test_summary_excerpt_skips_headings_and_handles_empty() -> None:
    # All-headings body -> no paragraph -> "".
    assert _summary_excerpt("# Title\n\n## Summary\n\n### Detail") == ""
    # Empty body -> "".
    assert _summary_excerpt("") == ""
    # Normal body -> first non-heading paragraph, truncated to the limit.
    body = "## Summary\n\nThe first real paragraph of prose.\n\nA second one."
    assert _summary_excerpt(body) == "The first real paragraph of prose."
    # Truncation at the 280-char limit.
    long_para = "## Summary\n\n" + "x" * 400
    assert _summary_excerpt(long_para) == "x" * 280
