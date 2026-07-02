"""Tests for the PHASE-15 two-step deterministic leg-history assembler.

`merge_lanes` (pure) is the shared deterministic merge both CLI steps call, so the
verifier is dispatched over a Python-numbered list and the assembler re-merges to the
byte-identical order — the verdict<->statement index alignment is correct by construction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.pipeline.leg_history import LANE_ORDER, merge_lanes

runner = CliRunner()

# Quotes long enough to clear the model's min_length=20 floor; distinct per lane so
# order assertions are unambiguous.
_QUOTE_CREC = "We must protect consumers from harmful automated systems today."
_QUOTE_PRESS = "This bill establishes a new accountability office for algorithms."
_QUOTE_SIGNING = "I am proud to sign this measure protecting Americans from misuse."


def _statement(
    *,
    speaker: str = "Rep. Jane Doe",
    quote: str = _QUOTE_CREC,
    source_url: str = "https://www.congress.gov/x",
    source_type: str = "CREC",
    role: str = "sponsor",
    relation: str = "on_bill",
) -> dict[str, object]:
    return {
        "speaker": speaker,
        "role": role,
        "quote": quote,
        "source_url": source_url,
        "source_type": source_type,
        "verified": False,
        "relation": relation,
    }


def _hearing(
    *,
    title: str = "Hearing on AI",
    url: str | None = "https://example.gov/h1",
    relation: str = "on_bill",
) -> dict[str, object]:
    return {"title": title, "url": url, "relation": relation}


def _media(
    *,
    title: str = "Markup video",
    url: str = "https://www.youtube.com/watch?v=abc",
    kind: str = "video",
    relation: str = "on_bill",
) -> dict[str, object]:
    return {"title": title, "url": url, "kind": kind, "relation": relation}


def _lane(
    *,
    statements: list[dict[str, object]] | None = None,
    hearings: list[dict[str, object]] | None = None,
    related_media: list[dict[str, object]] | None = None,
    narrative: str = "",
) -> dict[str, object]:
    return {
        "statements": statements or [],
        "hearings": hearings or [],
        "related_media": related_media or [],
        "narrative": narrative,
    }


def test_lane_order_is_crec_hearings_press_signing() -> None:
    """should fix the canonical lane merge order"""
    assert LANE_ORDER == ("crec", "hearings", "press", "signing")


def test_merge_lanes_orders_statements_by_fixed_lane_order_not_dict_order() -> None:
    """should concatenate statements in LANE_ORDER regardless of input dict order"""
    lanes = {
        "press": _lane(statements=[_statement(quote=_QUOTE_PRESS)]),
        "crec": _lane(statements=[_statement(quote=_QUOTE_CREC)]),
        "signing": _lane(statements=[_statement(quote=_QUOTE_SIGNING, source_type="signing")]),
    }
    merged = merge_lanes(lanes)
    assert [s.quote for s in merged.statements] == [_QUOTE_CREC, _QUOTE_PRESS, _QUOTE_SIGNING]


def test_merge_lanes_dedups_statements_by_speaker_and_quote() -> None:
    """should keep the first occurrence of a (speaker, quote) seen across lanes"""
    dup = _statement(speaker="Rep. Doe", quote=_QUOTE_CREC)
    lanes = {
        "crec": _lane(statements=[dup]),
        "press": _lane(statements=[dict(dup)]),
    }
    merged = merge_lanes(lanes)
    assert len(merged.statements) == 1


def test_merge_lanes_dedups_related_media_by_url() -> None:
    """should drop a later related-media item that repeats an already-seen url"""
    first = _media(url="https://www.youtube.com/watch?v=abc")
    lanes = {
        "hearings": _lane(related_media=[first]),
        "press": _lane(related_media=[_media(title="Different title", url="https://www.youtube.com/watch?v=abc")]),
    }
    merged = merge_lanes(lanes)
    assert len(merged.related_media) == 1
    assert merged.related_media[0].title == "Markup video"


def test_merge_lanes_keeps_urlless_hearings_and_dedups_by_url() -> None:
    """should dedup hearings sharing a url but never collapse distinct url-less hearings"""
    lanes = {
        "hearings": _lane(
            hearings=[
                _hearing(url="https://example.gov/h1"),
                _hearing(title="Other", url="https://example.gov/h1"),
                _hearing(title="No url A", url=None),
                _hearing(title="No url B", url=None),
            ]
        ),
    }
    merged = merge_lanes(lanes)
    urls = [h.url for h in merged.hearings]
    assert urls.count("https://example.gov/h1") == 1
    assert urls.count(None) == 2


def test_merge_lanes_takes_narrative_from_crec_lane_only() -> None:
    """should source the narrative from the crec lane and ignore other lanes' narrative"""
    lanes = {
        "crec": _lane(narrative="The legislative journey."),
        "press": _lane(narrative="IGNORE ME"),
    }
    merged = merge_lanes(lanes)
    assert merged.narrative == "The legislative journey."


def test_merge_lanes_narrative_is_none_when_crec_lane_absent() -> None:
    """should leave narrative None when the crec lane is missing"""
    lanes = {"press": _lane(narrative="not the narrative")}
    merged = merge_lanes(lanes)
    assert merged.narrative is None


def test_merge_lanes_drops_a_malformed_lane_and_keeps_the_rest() -> None:
    """should drop a lane whose top-level payload is not an object and record it"""
    lanes = {
        "crec": _lane(statements=[_statement(quote=_QUOTE_CREC)]),
        "press": ["not", "a", "dict"],
    }
    merged = merge_lanes(lanes)
    assert "press" in merged.dropped_lanes
    assert len(merged.statements) == 1


def test_merge_lanes_drops_a_missing_lane_passed_as_none() -> None:
    """should treat a None lane payload (unreadable file) as a dropped lane"""
    lanes = {"crec": _lane(statements=[_statement(quote=_QUOTE_CREC)]), "signing": None}
    merged = merge_lanes(lanes)
    assert "signing" in merged.dropped_lanes
    assert len(merged.statements) == 1


def test_merge_lanes_parse_drops_a_malformed_item_but_keeps_valid_ones() -> None:
    """should parse-drop an individual malformed statement without dropping the lane"""
    lanes = {
        "crec": _lane(statements=[_statement(quote=_QUOTE_CREC), {"speaker": "Missing fields"}]),
    }
    merged = merge_lanes(lanes)
    assert len(merged.statements) == 1
    assert len(merged.parse_dropped) == 1


# --- CLI fixtures -----------------------------------------------------------


def _bill() -> dict[str, object]:
    return {
        "type": "bill",
        "id": "118-hr-9020",
        "jurisdiction": "US",
        "title": "Test Act",
        "bill_number": "H.R. 9020",
        "summary": "A test bill.",
        "status": "enacted",
        "topics": ["ai"],
        "sponsors": ["Rep. Jane Doe"],
        "actions": [],
        "amendments": [],
    }


def _spine() -> dict[str, object]:
    return {
        "versions": [],
        "committee_reports": [],
        "votes": [],
        "floor_consideration": [],
        "hearings": [],
        "statements": [],
        "related_media": [],
        "enactment": None,
        "narrative": None,
    }


def _write_run(
    run: Path,
    *,
    lane_files: dict[str, dict[str, object]],
    leghistory: dict[str, object] | None = None,
) -> None:
    """Write a run dir: leghistory.json + lane-<name>.json for each provided lane."""
    run.mkdir(parents=True, exist_ok=True)
    payload = leghistory or {"bill": _bill(), "spine": _spine(), "leads": {}}
    (run / "leghistory.json").write_text(json.dumps(payload), encoding="utf-8")
    for lane, body in lane_files.items():
        (run / f"lane-{lane}.json").write_text(json.dumps(body), encoding="utf-8")


# --- build-verifier-input ---------------------------------------------------


def test_build_verifier_input_writes_subject_block_from_the_bill(tmp_path: Path) -> None:
    """should write a subject block carrying the bill's citation, title, topics, sponsors"""
    run = tmp_path / "run"
    crec = _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="J")
    _write_run(run, lane_files={"crec": crec})

    result = runner.invoke(app, ["build-verifier-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    vin = json.loads((run / "verifier-input.json").read_text(encoding="utf-8"))
    assert vin["subject"] == {
        "citation": "H.R. 9020",
        "title": "Test Act",
        "topics": ["ai"],
        "sponsors": ["Rep. Jane Doe"],
    }


def test_build_verifier_input_stamps_indices_in_merged_order(tmp_path: Path) -> None:
    """should index statements/media by their merged position across lanes in fixed order"""
    run = tmp_path / "run"
    _write_run(
        run,
        lane_files={
            "press": _lane(statements=[_statement(quote=_QUOTE_PRESS, source_type="press")]),
            "crec": _lane(statements=[_statement(quote=_QUOTE_CREC)]),
            "hearings": _lane(related_media=[_media()]),
        },
    )

    result = runner.invoke(app, ["build-verifier-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    vin = json.loads((run / "verifier-input.json").read_text(encoding="utf-8"))
    # crec lane sorts before press regardless of file/dict order.
    assert [(s["index"], s["quote"]) for s in vin["statements"]] == [
        (0, _QUOTE_CREC),
        (1, _QUOTE_PRESS),
    ]
    assert vin["statements"][0]["source_url"] == "https://www.congress.gov/x"
    assert vin["statements"][0]["relation"] == "on_bill"
    assert vin["related_media"][0]["index"] == 0
    assert vin["related_media"][0]["url"] == "https://www.youtube.com/watch?v=abc"
    assert vin["related_media"][0]["kind"] == "video"


def test_build_verifier_input_errors_when_leghistory_missing(tmp_path: Path) -> None:
    """should exit non-zero when the run dir has no leghistory.json"""
    run = tmp_path / "run"
    run.mkdir()
    result = runner.invoke(app, ["build-verifier-input", "--run-dir", str(run)])
    assert result.exit_code == 1, result.output


# --- assemble-leg-history-input ---------------------------------------------


def _write_verifier(
    run: Path,
    *,
    statements: list[dict[str, object]] | None = None,
    related_media: list[dict[str, object]] | None = None,
    narrative: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "statements": statements or [],
        "related_media": related_media or [],
    }
    if narrative is not None:
        payload["narrative"] = narrative
    (run / "verifier.json").write_text(json.dumps(payload), encoding="utf-8")


def test_assemble_attaches_verdicts_keyed_by_merged_index(tmp_path: Path) -> None:
    """should write a render-input with merged statements/media + verdicts keyed by merged index"""
    run = tmp_path / "run"
    _write_run(
        run,
        lane_files={
            "crec": _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="Journey."),
            "hearings": _lane(related_media=[_media()]),
        },
    )
    _write_verifier(
        run,
        statements=[
            {
                "index": 0,
                "speaker": "Rep. Jane Doe",
                "quote_prefix": _QUOTE_CREC[:40],
                "on_subject": True,
                "verified": True,
                "note": "ok",
            }
        ],
        related_media=[
            {"index": 0, "title_prefix": "Markup video", "verified": True, "note": "ok"}
        ],
    )

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    assert render_input["bill"]["id"] == "118-hr-9020"
    assert render_input["spine"]["versions"] == []
    assert render_input["narrative"] == "Journey."
    assert render_input["statements"][0]["quote"] == _QUOTE_CREC
    assert render_input["verdicts"][0] == {
        "index": 0,
        "speaker": "Rep. Jane Doe",
        "quote_prefix": _QUOTE_CREC[:40],
        "verified": True,
        "note": "ok",
    }
    assert render_input["media_verdicts"][0]["index"] == 0
    assert render_input["media_verdicts"][0]["verified"] is True


def test_assemble_downgrades_verdict_on_speaker_echo_mismatch(tmp_path: Path) -> None:
    """should fail-closed (verified:false) when the verifier echoes a different speaker"""
    run = tmp_path / "run"
    _write_run(run, lane_files={"crec": _lane(statements=[_statement(quote=_QUOTE_CREC)])})
    _write_verifier(
        run,
        statements=[
            {
                "index": 0,
                "speaker": "Sen. Someone Else",
                "quote_prefix": _QUOTE_CREC[:40],
                "on_subject": True,
                "verified": True,
                "note": "ok",
            }
        ],
    )

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    assert render_input["verdicts"][0]["verified"] is False


def test_assemble_marks_statement_without_a_verdict_unverified(tmp_path: Path) -> None:
    """should emit a verified:false verdict for a merged statement the verifier did not score"""
    run = tmp_path / "run"
    _write_run(run, lane_files={"crec": _lane(statements=[_statement(quote=_QUOTE_CREC)])})
    _write_verifier(run, statements=[])

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    assert render_input["verdicts"][0]["index"] == 0
    assert render_input["verdicts"][0]["verified"] is False


def test_assemble_errors_when_verifier_json_missing(tmp_path: Path) -> None:
    """should exit non-zero when verifier.json is absent"""
    run = tmp_path / "run"
    _write_run(run, lane_files={"crec": _lane(statements=[_statement(quote=_QUOTE_CREC)])})
    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 1, result.output


def test_assembler_output_renders_through_render_leg_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should produce a render-input that render-leg-history grounds and renders end-to-end"""

    def _fake_fetch(url: str) -> tuple[int, str]:
        if url == "https://www.congress.gov/x":
            return (200, f"Congressional Record: {_QUOTE_CREC} The speaker continued.")
        return (404, "Not Found")

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)

    run = tmp_path / "run"
    crec = _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="Journey.")
    _write_run(run, lane_files={"crec": crec})
    _write_verifier(
        run,
        statements=[
            {
                "index": 0,
                "speaker": "Rep. Jane Doe",
                "quote_prefix": _QUOTE_CREC[:40],
                "on_subject": True,
                "verified": True,
                "note": "ok",
            }
        ],
    )

    assert runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)]).exit_code == 0

    wiki = tmp_path / "wiki"
    result = runner.invoke(
        app,
        ["render-leg-history", "--in", str(run / "leghistory-research.json"), "--wiki", str(wiki)],
    )
    assert result.exit_code == 0, result.output
    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert _QUOTE_CREC in rendered


# --- narrative verdict plumbing (D106) ---------------------------------------


def test_build_verifier_input_carries_narrative_and_spine_digest(tmp_path: Path) -> None:
    """should write the merged narrative plus a votes/timeline/enactment spine digest"""
    run = tmp_path / "run"
    crec = _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="Journey.")
    leghistory: dict[str, object] = {"bill": _bill(), "spine": _spine(), "leads": {}}
    spine = leghistory["spine"]
    assert isinstance(spine, dict)
    spine["votes"] = [
        {"date": "2024-05-01", "chamber": "House", "result": "Passed 100-0", "roll_call_url": None}
    ]
    _write_run(run, lane_files={"crec": crec}, leghistory=leghistory)

    result = runner.invoke(app, ["build-verifier-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    vin = json.loads((run / "verifier-input.json").read_text(encoding="utf-8"))
    assert vin["narrative"] == "Journey."
    assert vin["spine"]["votes"] == [
        {"date": "2024-05-01", "chamber": "House", "result": "Passed 100-0", "roll_call_url": None}
    ]
    assert vin["spine"]["timeline"] == []
    assert vin["spine"]["enactment"] is None


def test_assemble_passes_through_a_pass_narrative_verdict(tmp_path: Path) -> None:
    """should write narrative_verdict pass when the verifier's narrative block says pass"""
    run = tmp_path / "run"
    crec = _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="Journey.")
    _write_run(run, lane_files={"crec": crec})
    _write_verifier(
        run,
        statements=[
            {
                "index": 0,
                "speaker": "Rep. Jane Doe",
                "quote_prefix": _QUOTE_CREC[:40],
                "on_subject": True,
                "verified": True,
                "note": "ok",
            }
        ],
        narrative={"checked": True, "verdict": "pass", "issues": []},
    )

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    assert render_input["narrative_verdict"] == {"checked": True, "verdict": "pass", "issues": []}


def test_assemble_fails_closed_when_verifier_has_no_narrative_block(tmp_path: Path) -> None:
    """should write a fail narrative_verdict when the verifier returned no narrative block"""
    run = tmp_path / "run"
    crec = _lane(statements=[_statement(quote=_QUOTE_CREC)], narrative="Journey.")
    _write_run(run, lane_files={"crec": crec})
    _write_verifier(run, statements=[])

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    verdict = render_input["narrative_verdict"]
    assert verdict["checked"] is True
    assert verdict["verdict"] == "fail"


def test_assemble_marks_missing_narrative_unchecked(tmp_path: Path) -> None:
    """should write checked false when there is no merged narrative to verify"""
    run = tmp_path / "run"
    press = _lane(statements=[_statement(quote=_QUOTE_PRESS, source_type="press")])
    _write_run(run, lane_files={"press": press})
    _write_verifier(run, statements=[])

    result = runner.invoke(app, ["assemble-leg-history-input", "--run-dir", str(run)])
    assert result.exit_code == 0, result.output

    render_input = json.loads((run / "leghistory-research.json").read_text(encoding="utf-8"))
    assert render_input["narrative_verdict"] == {"checked": False}
