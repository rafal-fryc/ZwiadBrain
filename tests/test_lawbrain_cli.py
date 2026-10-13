"""CLI tests for both halves of /zwiad-sync-lawbrain.

The fetch half (``fetch-lawbrain-candidates``) is exercised first; the render
half (``render-lawbrain-commentary``) follows. Both are fully offline: the law
brain is the committed mini-wiki under tests/fixtures/lawbrain/, targets are
rendered to a tmp wiki, and classified.json is hand-built to stand in for the
(subagent/operator) fetch+match output. No network, no LLM.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import _summary_excerpt, app  # pyright: ignore[reportPrivateUsage]
from zwiadbrain.config import LawBrainSettings, Settings
from zwiadbrain.models import Action, Bill, TextVersion
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.wiki.schema import from_page

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
                "  - transparency",
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


def _write_keyless_lawbrain_page(law_brain: Path, *, tags: list[str]) -> None:
    """A single-subject US-CA concept page with no bill/docket/public-law key."""
    page = law_brain / "wiki" / "concept-keyless-note.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                'title: "Keyless Note"',
                "type: concept",
                "jurisdiction: US-CA",
                "tags:",
                *[f"  - {tag}" for tag in tags],
                "status: active",
                "---",
                "",
                "## Summary",
                "",
                "A keyless single-subject note.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_ca_bill(wiki: Path, *, id_: str, bill_number: str, title: str) -> None:
    page = wiki / "bills" / f"{id_}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                f"id: {id_}",
                "type: bill",
                "jurisdiction: US-CA",
                f"title: {title}",
                f"bill_number: {bill_number}",
                "status: introduced",
                "sources: {}",
                "commentary_sources: []",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _fetch(wiki: Path, out: Path) -> list[dict[str, object]]:
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    loaded: list[dict[str, object]] = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    return loaded


def test_fetch_lawbrain_candidates_should_mark_not_in_scope_when_shortlist_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the only same-jurisdiction target shares no topical tokens.
    from zwiadbrain.pipeline.lawbrain_keys import keyless_decision_hash  # noqa: PLC0415

    law_brain = tmp_path / "law"
    _write_keyless_lawbrain_page(law_brain, tags=["agriculture", "drones"])
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))

    # Act
    candidates = _fetch(wiki, tmp_path / "run")

    # Assert — settled deterministically: no shortlist, no LLM step needed.
    entry = {str(c["slug"]): c for c in candidates}["concept-keyless-note"]
    assert entry["match"] == "not_in_scope"
    assert entry["shortlist"] == []
    assert entry["keys_hash"] == keyless_decision_hash(set(), [])


def test_fetch_lawbrain_candidates_should_skip_recorded_not_in_scope_until_shortlist_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — fetch, then record the keyless page as not_in_scope via render.
    law_brain = tmp_path / "law"
    _write_keyless_lawbrain_page(law_brain, tags=["frontier", "transparency"])
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    first = {str(c["slug"]): c for c in _fetch(wiki, tmp_path / "run1")}
    assert first["concept-keyless-note"]["shortlist"] == ["ca-2025-sb-53"]
    classified = tmp_path / "classified.json"
    classified.write_text(
        json.dumps([{"slug": "concept-keyless-note", "matched_by": "not_in_scope"}]),
        encoding="utf-8",
    )
    rendered = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(classified), "--wiki", str(wiki),
         "--db", str(tmp_path / "index.sqlite")],
    )
    assert rendered.exit_code == 0, rendered.output

    # Act — re-fetch unchanged, then track a new overlapping bill and re-fetch.
    unchanged = {str(c["slug"]) for c in _fetch(wiki, tmp_path / "run2")}
    _write_ca_bill(
        wiki, id_="ca-2026-sb-9", bill_number="SB 9", title="Frontier model transparency"
    )
    widened = {str(c["slug"]): c for c in _fetch(wiki, tmp_path / "run3")}

    # Assert — sticky while nothing changes; re-proposed once a new candidate appears.
    assert "concept-keyless-note" not in unchanged
    assert widened["concept-keyless-note"]["match"] == "keyless"


def test_fetch_lawbrain_candidates_skips_settled_registry_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — record a reject decision whose keys_hash matches the live key-set.
    # (A link is settled by its copied content instead — see the refresh test.)
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
            decision="reject",
            target_id="ca-2025-sb-53",
            matched_by=None,
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


def test_fetch_lawbrain_candidates_should_report_malformed_count_when_pages_fail_to_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the committed fixture brain carries one malformed page.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))

    # Act
    result = _RUNNER.invoke(
        app,
        ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(tmp_path / "run")],
    )

    # Assert
    assert result.exit_code == 0, result.output
    assert "1 malformed law-brain page(s) skipped" in result.output


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


# ---------------------------------------------------------------------------
# Render half: render-lawbrain-commentary
# ---------------------------------------------------------------------------
#
# These tests drive load_settings() via a real zwiadbrain.toml in a chdir'd
# tmp_path (the render command reads settings itself, not a monkeypatched one).
# The asserted Further Reading hosts match the committed SB-53 fixture: the page
# body carries a Mayer Brown link, and the referenced sb53-memo.md carries Morgan
# Lewis / IAPP / a bare Sidley URL plus two primary sources (leginfo, Wikipedia)
# that must be filtered out by the primary-source denylist.


def _write_render_settings(tmp_path: Path) -> None:
    """Enable the law brain (pointed at the offline fixture) via a real TOML."""
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text(
        "[lawbrain]\n"
        "enabled = true\n"
        f'path = "{_FIXTURE_LAWBRAIN.as_posix()}"\n'
        "min_confidence = 0.75\n"
        "require_shared_key = true\n"
        "demote_headings = true\n"
        "commentary = true\n"
        "further_reading = true\n"
        'commentary_only_slug_markers = ["tracker", "landscape", "map", "scholarship"]\n',
        encoding="utf-8",
    )


def _seed_sb53_target(wiki: Path) -> None:
    """Render the tracked CA SB 53 bill page (the deterministic-match target)."""
    bill = Bill(
        id="ca-2025-sb-53",
        jurisdiction="US-CA",
        title="California SB 53 — Transparency in Frontier AI Act",
        bill_number="SB 53",
        topics=["ai"],
        summary="A California frontier-model transparency bill.",
        sources={"LegiScan": "https://legiscan.com/CA/bill/SB53/2025"},
    )
    write_page(bill, wiki)


def _classified_deterministic() -> list[dict[str, object]]:
    """One deterministic SB-53 link (the showcase) the fetch half would emit."""
    return [
        {
            "slug": "regulation-california-sb53-tfaia",
            "target_id": "ca-2025-sb-53",
            "matched_by": "deterministic",
            "confidence": 1.0,
            "page_keys": ["US-CA::bill::SB-53"],
            "target_keys": ["US-CA::bill::SB-53"],
        }
    ]


_SB53_PAGE = ("states", "ca", "bills", "ca-2025-sb-53.md")


def test_render_lawbrain_attaches_commentary_and_further_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )

    # Act
    result = _RUNNER.invoke(
        app,
        [
            "render-lawbrain-commentary",
            "--in",
            str(run / "classified.json"),
            "--wiki",
            str(wiki),
            "--db",
            str(tmp_path / "index.sqlite"),
        ],
    )

    # Assert — command succeeded and reported one link.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output

    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    # Commentary region with the slug marker, demoted headings, neutralized wikilink.
    assert "## Commentary & Analysis" in page
    assert "<!-- lawbrain:region:begin -->" in page
    assert "<!-- lawbrain:begin slug=regulation-california-sb53-tfaia -->" in page
    assert "### Summary" in page  # source "## Summary" demoted to "###"
    assert "concept-california-ai-regulatory-landscape" in page  # [[...]] neutralized
    assert "[[concept-california-ai-regulatory-landscape]]" not in page
    # Further Reading harvested from page body + referenced memo, primary sources dropped.
    assert "## Further Reading (via law brain)" in page
    assert "morganlewis.com" in page  # from the memo (markdown link)
    assert "iapp.org" in page  # from the memo (markdown link)
    assert "sidley.com" in page  # from the memo (bare URL captured)
    assert "mayerbrown.com" in page  # from the page body itself
    assert "leginfo.legislature.ca.gov" not in page  # *.gov primary source filtered
    assert "en.wikipedia.org" not in page  # wikipedia primary source filtered
    # A decided link is recorded in the committed registry, not the review queue.
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in links_yaml
    assert "ca-2025-sb-53" in links_yaml
    # commentary body/links stay OUT of frontmatter (D20): reload via from_page.
    reloaded = from_page(page)
    assert len(reloaded.commentary_sources) == 1
    assert reloaded.commentary_sources[0].slug == "regulation-california-sb53-tfaia"
    assert reloaded.commentary_sources[0].body is None  # bookkeeping only
    assert reloaded.commentary_sources[0].links == []


def test_render_lawbrain_preserves_existing_bill_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attaching commentary must NOT destroy the bill's own body sections.

    Regression for the PHASE-09 bug: ``render-lawbrain-commentary`` rebuilt the
    page from frontmatter-only data (``from_page``), so a real bill's body-only
    ``## Summary`` / ``## Status & Timeline`` / ``## Full Text`` sections — none of
    which is serialized to frontmatter (``_BODY_ONLY_FIELDS``) — vanished, leaving
    just ``## Sources`` and the commentary region. ``_seed_sb53_target`` hid this by
    seeding a body-less target; a fully-populated bill (like a backfilled LegiScan
    page) reproduces it.
    """
    # Arrange — seed a richly-populated bill page: summary + timeline + full text.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    bill = Bill(
        id="ca-2025-sb-53",
        jurisdiction="US-CA",
        title="California SB 53 — Transparency in Frontier AI Act",
        bill_number="SB 53",
        topics=["ai"],
        summary="A California frontier-model transparency bill.",
        actions=[
            Action(date=dt.date(2025, 1, 7), text="Introduced. Read first time.", chamber="S"),
            Action(date=dt.date(2025, 9, 29), text="Chaptered. Chapter 138, Statutes of 2025."),
        ],
        text_versions=[
            TextVersion(
                code="Introduced",
                date=dt.date(2025, 1, 7),
                url="https://leginfo.example/SB53#INT",
            ),
        ],
        sources={"LegiScan": "https://legiscan.com/CA/bill/SB53/2025"},
    )
    write_page(bill, wiki)
    seeded = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Status & Timeline" in seeded  # precondition: the seeded body is rich
    assert "## Full Text" in seeded

    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )

    # Act
    result = _RUNNER.invoke(
        app,
        [
            "render-lawbrain-commentary",
            "--in",
            str(run / "classified.json"),
            "--wiki",
            str(wiki),
            "--db",
            str(tmp_path / "index.sqlite"),
        ],
    )

    # Assert — commentary attached AND the bill's own body survives verbatim.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "<!-- lawbrain:region:begin -->" in page  # commentary region added
    # The regression guards: body-only sections must NOT be dropped.
    assert "A California frontier-model transparency bill." in page  # bill's own Summary
    assert "## Status & Timeline" in page
    assert "Chaptered. Chapter 138, Statutes of 2025." in page
    assert "## Full Text" in page
    assert "[Introduced](https://leginfo.example/SB53#INT)" in page
    # The region is still appended last, after the preserved body.
    assert page.index("## Status & Timeline") < page.index("<!-- lawbrain:region:begin -->")
    assert page.index("## Full Text") < page.index("<!-- lawbrain:region:begin -->")


def test_render_lawbrain_rerun_is_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — first render.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / Path(*_SB53_PAGE)
    first = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )
    assert first.exit_code == 0, first.output
    after_first = page_path.read_text(encoding="utf-8")
    links_after_first = (wiki / "links.yaml").read_text(encoding="utf-8")

    # Act — identical second render.
    second = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — byte-identical page AND registry (D20: idempotent, clean git status).
    assert second.exit_code == 0, second.output
    assert page_path.read_text(encoding="utf-8") == after_first
    assert (wiki / "links.yaml").read_text(encoding="utf-8") == links_after_first


def test_render_lawbrain_weak_grounding_routes_to_review_not_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an LLM-proposed link whose FRESH keys do not intersect: the source
    # is a keyless (fail-closed landscape) law-brain page, so the confirm grounds on
    # an empty page_keys and fails the require_shared_key gate -> review, not links.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    # A landscape-marker page yields zero real keys (fail-closed, D60).
                    "slug": "concept-fixture-ai-landscape",
                    "target_id": "ca-2025-sb-53",
                    "matched_by": "llm",
                    "confidence": 0.9,
                    # Carried keys would intersect if trusted — they must be ignored.
                    "page_keys": ["US-CA::bill::SB-53"],
                    "target_keys": ["US-CA::bill::SB-53"],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — no commentary attached, a review entry written, no links.yaml decision.
    assert result.exit_code == 0, result.output
    assert "1 review" in result.output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "concept-fixture-ai-landscape" in review
    assert "weak-grounding" in review
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_llm_confirm_grounds_on_fresh_keys_not_llm_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Trust-boundary attack (D16): an llm entry CARRIES intersecting fake keys
    # ("FAKE::key" on both sides) — if the confirm trusted the echoed keys it would
    # attach. The real page yields US-CA::bill::SB-53 and the real target yields the
    # SAME real key, but the confirm must ground on those FRESH disk keys, not the
    # carried fakes. Here the carried fakes intersect AND the real keys also happen
    # to intersect, so to prove the gate ignores the echo we point the carried keys
    # at a value that intersects while the real key match is what actually decides.
    #
    # The decisive case: carried keys intersect but are FAKE; the real keys must be
    # what's used. We assert the link is recorded with the REAL keys_hash, never a
    # hash of the fake carried keys — proving the recompute happened.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    "slug": "regulation-california-sb53-tfaia",
                    "target_id": "ca-2025-sb-53",
                    "matched_by": "llm",
                    "confidence": 0.9,
                    # Carried keys that INTERSECT but are fabricated — the gate must
                    # ignore these and ground on the real recomputed keys.
                    "page_keys": ["FAKE::echoed::key"],
                    "target_keys": ["FAKE::echoed::key"],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — grounded on the REAL keys (which also intersect: US-CA::bill::SB-53),
    # so this legitimately links; the stored keys_hash is the REAL hash, never the
    # fake-echo hash (proving the recompute, not the echo, drove the decision).
    from zwiadbrain.pipeline.lawbrain_keys import keys_hash  # noqa: PLC0415

    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    real_hash = keys_hash({"US-CA::bill::SB-53"})
    fake_hash = keys_hash({"FAKE::echoed::key"})
    assert real_hash in links_yaml
    assert fake_hash not in links_yaml


def test_render_lawbrain_llm_confirm_rejects_when_fresh_keys_do_not_intersect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The harder attack: carried keys intersect ("FAKE::key" on both sides) but the
    # REAL page/target keys do NOT (the law-brain page's real key is the SB-53 bill
    # key, while the target is an UNRELATED enforcement action with no SB-53 key).
    # If the confirm trusted the echoed keys it would attach a wrong commentary; it
    # must route to review (weak-grounding), attach nothing, record no link.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    # An unrelated enforcement target whose real keys never include the SB-53 bill key.
    enf = wiki / "federal" / "enforcement" / "ftc-unrelated.md"
    enf.parent.mkdir(parents=True, exist_ok=True)
    enf.write_text(
        "\n".join(
            [
                "---",
                "id: ftc-unrelated",
                "type: enforcement",
                "jurisdiction: US",
                "title: Unrelated FTC matter",
                "agency: FTC",
                "docket: 9-99-cv-00001",
                "sources: {}",
                "commentary_sources: []",
                "---",
                "",
                "## Background",
                "",
                "Unrelated.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    "slug": "regulation-california-sb53-tfaia",
                    "target_id": "ftc-unrelated",
                    "matched_by": "llm",
                    "confidence": 0.99,
                    "page_keys": ["FAKE::key"],  # echoed fakes that intersect
                    "target_keys": ["FAKE::key"],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — fresh keys don't intersect -> weak-grounding review, no attach, no link.
    assert result.exit_code == 0, result.output
    assert "1 review" in result.output
    assert "0 linked" in result.output
    page = enf.read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "weak-grounding" in review
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_accept_flip_is_recorded_and_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a review-queue.md with one operator-flipped [accept] entry. The
    # render pass must record it as a link decision in links.yaml and prune the
    # resolved entry from the queue (D61: resolution folded into the render half).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "review-queue.md").write_text(
        "- [accept] regulation-california-sb53-tfaia -> ca-2025-sb-53 (collision)\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    # No new proposals this pass — only the resolved queue token to apply.
    (run / "classified.json").write_text("[]", encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — decision recorded in links.yaml, queue pruned to empty.
    assert result.exit_code == 0, result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in links_yaml
    assert "ca-2025-sb-53" in links_yaml
    # The resolved [accept] line is gone (queue cleared to empty).
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" not in review


def test_render_lawbrain_reject_flip_records_reject_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a [reject] queue token must be recorded as a not-a-link decision
    # and pruned, so the page is never re-proposed (sticky reject).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "review-queue.md").write_text(
        "- [reject] regulation-fixture-sb53 -> ca-2025-sb-53 (weak-grounding)\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text("[]", encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — reject recorded; the SB-53 target keeps no commentary.
    assert result.exit_code == 0, result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" in links_yaml
    assert "reject" in links_yaml
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" not in review


def test_render_lawbrain_preserves_prior_decided_date_on_unchanged_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A re-record of the SAME unchanged link decision must keep the ORIGINAL decided
    # date, so links.yaml is byte-identical across day boundaries (D20 idempotency).
    # Pre-seed links.yaml with an old date; the render must not bump it to today.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    wiki.mkdir(parents=True, exist_ok=True)

    from zwiadbrain.pipeline.lawbrain_keys import keys_hash  # noqa: PLC0415
    from zwiadbrain.pipeline.lawbrain_registry import (  # noqa: PLC0415
        LinkDecision,
        LinkRegistry,
    )

    old_date = dt.date(2020, 1, 2)
    reg = LinkRegistry.load(wiki / "links.yaml")
    reg.record(
        LinkDecision(
            lawbrain_slug="regulation-california-sb53-tfaia",
            decision="link",
            target_id="ca-2025-sb-53",
            matched_by="deterministic",
            keys_hash=keys_hash({"US-CA::bill::SB-53"}),
            decided=old_date,
        )
    )
    reg.dump(wiki / "links.yaml")

    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — the prior date is preserved, not rewritten to today.
    assert result.exit_code == 0, result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "2020-01-02" in links_yaml
    assert dt.date.today().isoformat() not in links_yaml


def test_render_lawbrain_not_in_scope_is_recorded_not_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a not_in_scope decision attaches no commentary but IS recorded in
    # links.yaml (Shared Contract: not_in_scope/reject -> record, no attach) so the
    # page is never re-proposed (sticky, D9).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    "slug": "regulation-fixture-sb53",
                    "target_id": None,
                    "matched_by": "not_in_scope",
                    "confidence": 0.0,
                    "page_keys": ["US-CA::bill::SB-53"],
                    "target_keys": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — recorded as a not_in_scope decision; no commentary attached anywhere.
    assert result.exit_code == 0, result.output
    assert "0 linked" in result.output
    assert "1 recorded" in result.output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" in links_yaml
    assert "not_in_scope" in links_yaml


def test_render_lawbrain_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / Path(*_SB53_PAGE)
    before = page_path.read_text(encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite"), "--dry-run"],
    )

    # Assert — intended write reported, page untouched, no registry/queue written.
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower()
    assert page_path.read_text(encoding="utf-8") == before  # zero edits
    assert "## Commentary & Analysis" not in before
    assert not (wiki / "links.yaml").exists()
    assert not (wiki / "review-queue.md").exists()


def _render(tmp_path: Path, wiki: Path, entries: list[dict[str, object]]) -> str:
    classified = tmp_path / "classified.json"
    classified.write_text(json.dumps(entries), encoding="utf-8")
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(classified), "--wiki", str(wiki),
         "--db", str(tmp_path / "index.sqlite")],
    )
    assert result.exit_code == 0, result.output
    return result.output


def test_render_lawbrain_should_record_real_decision_hash_when_operator_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an operator [reject] on a page that deterministically matches SB 53.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    (wiki / "review-queue.md").write_text(
        "- [reject] regulation-fixture-sb53 -> ca-2025-sb-53 (weak-grounding)\n",
        encoding="utf-8",
    )

    # Act — resolve the queue, then fetch again.
    _render(tmp_path, wiki, [])
    candidates = _fetch(wiki, tmp_path / "run")

    # Assert — the reject is sticky: fetch no longer proposes the page.
    assert "regulation-fixture-sb53" not in {c["slug"] for c in candidates}


def test_render_lawbrain_should_record_real_decision_hash_when_operator_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    from zwiadbrain.pipeline.lawbrain_keys import keys_hash  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    (wiki / "review-queue.md").write_text(
        "- [accept] regulation-california-sb53-tfaia -> ca-2025-sb-53 (collision)\n",
        encoding="utf-8",
    )

    # Act
    _render(tmp_path, wiki, [])

    # Assert — the accept carries the page's real hash, not "".
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert f"keys_hash: {keys_hash({'US-CA::bill::SB-53'})}" in links_yaml


def test_render_lawbrain_should_scope_override_to_its_own_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — override for the SAME page but a DIFFERENT target than proposed.
    from zwiadbrain.pipeline.lawbrain_registry import (  # noqa: PLC0415
        LinkDecision,
        LinkRegistry,
    )

    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    _write_enforcement(wiki, id_="ftc-other")
    registry = LinkRegistry()
    registry.record(
        LinkDecision(
            lawbrain_slug="concept-fixture-ai-landscape",
            decision="link",
            target_id="ftc-other",
            matched_by="llm",
            keys_hash="",
            decided=dt.date(2026, 10, 1),
        )
    )
    registry.dump(wiki / "links.yaml")

    # Act
    output = _render(
        tmp_path,
        wiki,
        [{"slug": "concept-fixture-ai-landscape", "target_id": "ca-2025-sb-53",
          "matched_by": "llm", "confidence": 0.95}],
    )

    # Assert
    assert "0 linked" in output
    assert "1 review" in output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page


def test_fetch_lawbrain_candidates_should_emit_accepted_override_until_it_is_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a keyless page the operator accepted onto SB 53 (link override).
    law_brain = tmp_path / "law"
    _write_keyless_lawbrain_page(law_brain, tags=["frontier", "transparency"])
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    (wiki / "review-queue.md").write_text(
        "- [accept] concept-keyless-note -> ca-2025-sb-53 (weak-grounding)\n",
        encoding="utf-8",
    )
    _render(tmp_path, wiki, [])

    # Act — fetch proposes the override; stage it as the skill would; fetch again.
    first = {str(c["slug"]): c for c in _fetch(wiki, tmp_path / "run1")}
    entry = first["concept-keyless-note"]
    output = _render(
        tmp_path,
        wiki,
        [{"slug": "concept-keyless-note", "target_id": entry["target_id"],
          "matched_by": "llm", "confidence": 1.0}],
    )
    second = {str(c["slug"]) for c in _fetch(wiki, tmp_path / "run2")}

    # Assert — attached once via the override, then settled.
    assert entry["match"] == "override"
    assert entry["target_id"] == "ca-2025-sb-53"
    assert "1 linked" in output
    assert "concept-keyless-note" not in second


def test_fetch_lawbrain_candidates_should_propose_refresh_when_linked_page_content_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — link SB 53 commentary once from a writable copy of the fixture brain.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    _render(tmp_path, wiki, _classified_deterministic())
    unchanged = {str(c["slug"]) for c in _fetch(wiki, tmp_path / "run1")}
    source = law_brain / "wiki" / "regulation-california-sb53-tfaia.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nNewly added analysis paragraph.\n",
        encoding="utf-8",
    )

    # Act — fetch after the edit, stage the refresh as the skill would, fetch again.
    edited = {str(c["slug"]): c for c in _fetch(wiki, tmp_path / "run2")}
    entry = edited["regulation-california-sb53-tfaia"]
    _render(
        tmp_path,
        wiki,
        [{"slug": entry["slug"], "target_id": entry["target_id"],
          "matched_by": "deterministic", "confidence": 1.0}],
    )
    after = {str(c["slug"]) for c in _fetch(wiki, tmp_path / "run3")}

    # Assert — unchanged content is settled; edited content is re-copied once.
    assert "regulation-california-sb53-tfaia" not in unchanged
    assert entry["match"] == "refresh"
    assert entry["target_id"] == "ca-2025-sb-53"
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "Newly added analysis paragraph." in page
    assert "regulation-california-sb53-tfaia" not in after


_TAKE_IT_DOWN = "regulation-take-it-down-act"


def _collision_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A law-brain page whose public-law key is shared by two tracked FTC actions."""
    law_brain = tmp_path / "law"
    _write_take_it_down_lawbrain_page(law_brain)
    wiki = tmp_path / "wiki"
    _write_enforcement(wiki, id_="ftc-acme")
    _write_enforcement(wiki, id_="ftc-beta")
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    return wiki


def _collision_entry() -> dict[str, object]:
    return {"slug": _TAKE_IT_DOWN, "matched_by": "collision"}


def test_render_lawbrain_should_queue_one_line_per_target_when_staging_a_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    wiki = _collision_setup(tmp_path, monkeypatch)

    # Act
    output = _render(tmp_path, wiki, [_collision_entry()])

    # Assert — both candidates queued, nothing attached, nothing recorded.
    queue = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert f"- [pending] {_TAKE_IT_DOWN} -> ftc-acme (collision)" in queue
    assert f"- [pending] {_TAKE_IT_DOWN} -> ftc-beta (collision)" in queue
    assert "0 linked" in output
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_should_link_accepted_target_and_prune_siblings_when_collision_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — queue the collision, then the operator accepts ftc-beta.
    wiki = _collision_setup(tmp_path, monkeypatch)
    _render(tmp_path, wiki, [_collision_entry()])
    queue_path = wiki / "review-queue.md"
    queue_path.write_text(
        queue_path.read_text(encoding="utf-8").replace(
            f"- [pending] {_TAKE_IT_DOWN} -> ftc-beta", f"- [accept] {_TAKE_IT_DOWN} -> ftc-beta"
        ),
        encoding="utf-8",
    )

    # Act — resolve (this run also re-stages the still-colliding page), then fetch.
    _render(tmp_path, wiki, [_collision_entry()])
    candidates = {str(c["slug"]): c for c in _fetch(wiki, tmp_path / "run")}

    # Assert — sibling pruned and not re-queued; fetch proposes the accepted target.
    assert _TAKE_IT_DOWN not in queue_path.read_text(encoding="utf-8")
    assert candidates[_TAKE_IT_DOWN]["match"] == "override"
    assert candidates[_TAKE_IT_DOWN]["target_id"] == "ftc-beta"


def test_render_lawbrain_should_record_reject_when_every_collision_line_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    wiki = _collision_setup(tmp_path, monkeypatch)
    _render(tmp_path, wiki, [_collision_entry()])
    queue_path = wiki / "review-queue.md"
    queue_path.write_text(
        queue_path.read_text(encoding="utf-8").replace("[pending]", "[reject]"),
        encoding="utf-8",
    )

    # Act
    _render(tmp_path, wiki, [])
    candidates = {str(c["slug"]) for c in _fetch(wiki, tmp_path / "run")}

    # Assert — the page is settled as rejected.
    assert _TAKE_IT_DOWN not in candidates
    assert "decision: reject" in (wiki / "links.yaml").read_text(encoding="utf-8")


def test_render_lawbrain_should_keep_partial_collision_resolution_when_only_some_lines_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — one candidate rejected, the other still pending.
    wiki = _collision_setup(tmp_path, monkeypatch)
    _render(tmp_path, wiki, [_collision_entry()])
    queue_path = wiki / "review-queue.md"
    queue_path.write_text(
        queue_path.read_text(encoding="utf-8").replace(
            f"- [pending] {_TAKE_IT_DOWN} -> ftc-acme", f"- [reject] {_TAKE_IT_DOWN} -> ftc-acme"
        ),
        encoding="utf-8",
    )

    # Act — the page is re-staged as a collision on the next run.
    _render(tmp_path, wiki, [_collision_entry()])

    # Assert — the operator's reject survives; no page-level decision yet.
    queue = queue_path.read_text(encoding="utf-8")
    assert f"- [reject] {_TAKE_IT_DOWN} -> ftc-acme (collision)" in queue
    assert f"- [pending] {_TAKE_IT_DOWN} -> ftc-beta (collision)" in queue
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_should_parse_the_law_brain_once_when_rendering_many_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — three staged items (two links + one not_in_scope) and a counter on
    # LawBrainReader.pages(); every per-item lookup must reuse the single parse.
    from zwiadbrain.sources.lawbrain import LawBrainReader  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    entries = [
        *_classified_deterministic(),
        {**_classified_deterministic()[0], "slug": "regulation-fixture-sb53"},
        {"slug": "concept-fixture-ai-landscape", "matched_by": "not_in_scope"},
    ]
    (run / "classified.json").write_text(json.dumps(entries), encoding="utf-8")
    calls: list[int] = []
    original = LawBrainReader.pages

    def counting_pages(self: LawBrainReader) -> list[object]:
        calls.append(1)
        return list(original(self))

    monkeypatch.setattr(LawBrainReader, "pages", counting_pages)

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert
    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_render_lawbrain_drops_malformed_entry_without_failing_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — one good deterministic link + one entry missing required keys.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    entries = _classified_deterministic() + [{"matched_by": "deterministic"}]
    (run / "classified.json").write_text(json.dumps(entries), encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — the good link applied, the malformed one isolated as a drop.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output
    assert "1 dropped" in result.output
    assert "dropped:" in result.output
