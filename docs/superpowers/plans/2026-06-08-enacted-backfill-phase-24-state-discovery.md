# PHASE-24 — State enacted discovery (LegiScan `getMasterList`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prior-session, enacted-only state discovery — `LegiScanSource.list_sessions()` + `list_session_enacted(session_id)` over `getMasterList`, and a `fetch-state-enacted-candidates` CLI — so the prior-years backfill ingests only state bills that became law.

**Architecture:** `getSessionList` maps a year → a prior `session_id`; `getMasterList(id=session_id)` returns every bill in that session with `status`/`title`/`description` per row (live-confirmed — the `Raw` variant lacks these). We keep `status == 4 (Passed)`, carry `title`+`description` onto the `Candidate` for **free** recall, then reuse the existing enrich → classify → summarize → render pipeline. `keyword_filter` is extended to match `title + summary` so the description text drives state recall (federal title-only behaviour is preserved since federal candidates have no `summary`).

**Tech Stack:** Python 3.12, typer, httpx, respx, pytest, pydantic. Implements PHASE-24 of `docs/superpowers/specs/2026-06-08-enacted-laws-backfill-design.md` (the state half of D84).

**Branch:** `feature/enacted-state-discovery` (already created off `main` + the spec-correction commit). **Do not switch branches.** Leave the pre-existing modified `uv.lock` untouched.

**Phase mapping:** spec PHASE-B = repo PHASE-24.

**Live shapes (probed 2026-06-08, ground truth for fixtures):**
- `getSessionList?state=ca` → `{"sessions": [{session_id, year_start, year_end, special, session_name}, …]}`. CA: `2016`=2023-24, `1791`=2021-22, `1624`=2019-20 (all `special: 0`).
- `getMasterList?id=1624` → `{"status":"OK","masterlist":{"session":{…}, "0":{bill_id, number, change_hash, url, status_date, status, last_action_date, last_action, title, description}, …}}`. CA 2019-20: 5,423 rows, **1,626 with `status==4`**; statuses seen: 1 Introduced, 2 Engrossed, 3 Enrolled, 4 Passed, 5 Vetoed, 6 Failed.

**Authoritative gate:** `uv run ruff check . && uv run pyright && uv run pytest -q` from repo root. (IDE LSP may show spurious "could not resolve zwiadbrain.pipeline.*" — that's an editable-install artifact; `uv run pyright` with no path args is authoritative.)

---

### Task 1: LegiScan discovery fixtures + live confirmation

**Files:**
- Create: `tests/fixtures/legiscan/getSessionList.json`
- Create: `tests/fixtures/legiscan/getMasterList.json`

- [ ] **Step 1: Write `tests/fixtures/legiscan/getSessionList.json`**

```json
{
  "status": "OK",
  "sessions": [
    {"session_id": 2016, "year_start": 2023, "year_end": 2024, "special": 0, "session_name": "2023-2024 Session"},
    {"session_id": 1791, "year_start": 2021, "year_end": 2022, "special": 0, "session_name": "2021-2022 Session"},
    {"session_id": 1624, "year_start": 2019, "year_end": 2020, "special": 0, "session_name": "2019-2020 Session"}
  ]
}
```

- [ ] **Step 2: Write `tests/fixtures/legiscan/getMasterList.json`** — mixed statuses: two enacted (`status==4`, one AI-topical / one not), one failed (`status==6`, privacy-topical — must be excluded by the status filter), plus the non-bill `session` member.

```json
{
  "status": "OK",
  "masterlist": {
    "session": {"session_id": 1624, "session_name": "2019-2020 Session", "year_start": 2019, "year_end": 2020},
    "0": {"bill_id": 1132030, "number": "AB1", "change_hash": "hashA", "status": 4, "status_date": "2019-07-31", "url": "https://legiscan.com/CA/bill/AB1/2019", "title": "Automated decision systems: artificial intelligence accountability.", "description": "An act to regulate automated decision systems and artificial intelligence."},
    "1": {"bill_id": 1132099, "number": "AB99", "change_hash": "hashB", "status": 4, "status_date": "2019-09-01", "url": "https://legiscan.com/CA/bill/AB99/2019", "title": "Youth athletics: California Youth Football Act.", "description": "An act to add Article 2.7 to the Health and Safety Code."},
    "2": {"bill_id": 1132200, "number": "SB200", "change_hash": "hashC", "status": 6, "status_date": "2019-05-01", "url": "https://legiscan.com/CA/bill/SB200/2019", "title": "Consumer privacy: data brokers.", "description": "An act concerning consumer privacy that failed passage."}
  }
}
```

- [ ] **Step 3: Confirm the real shapes live (one-shot, gated).** `.env` has `LEGISCAN_API_KEY`.

```
uv run python -c "import os,httpx,json; from dotenv import load_dotenv; load_dotenv(); k=os.environ['LEGISCAN_API_KEY']; b='https://api.legiscan.com/'; s=httpx.get(b,params={'key':k,'op':'getSessionList','state':'CA'},timeout=30).json(); print('sessions sample:', json.dumps(s.get('sessions',[])[:1])); m=httpx.get(b,params={'key':k,'op':'getMasterList','id':1624},timeout=90).json(); ml=m.get('masterlist',{}); rows=[v for kk,v in ml.items() if kk!='session']; print('row keys:', sorted(rows[0].keys())); print('has status/title/description:', all(x in rows[0] for x in ('status','title','description')))"
```

Expected: session objects carry `session_id`/`year_start`/`year_end`/`special`/`session_name`; masterlist rows carry `status`, `title`, `description` (+ `bill_id`, `number`, `change_hash`, `status_date`). **If a field name differs, update the fixtures to match the real response** and note the delta in the commit message. If no egress, proceed with the fixtures as written and report live-confirmation PENDING.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/legiscan/getSessionList.json tests/fixtures/legiscan/getMasterList.json
git commit -m "test(backfill): getSessionList + getMasterList fixtures for state enacted discovery"
```

---

### Task 2: `Session` dataclass + `LegiScanSource.list_sessions`

**Files:**
- Modify: `src/zwiadbrain/sources/legiscan.py`
- Test: `tests/test_legiscan.py`

- [ ] **Step 1: Write the failing test.** Add to `tests/test_legiscan.py` (the test helpers `_source`, `_fixture`, `_route_by_op`, `LEGISCAN_API_BASE` already exist):

```python
def test_list_sessions_maps_getsessionlist_to_sessions() -> None:
    """should map getSessionList entries to Session records for the state"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSessionList": _fixture("getSessionList.json")})
        sessions = _source().list_sessions()
    assert [s.session_id for s in sessions] == [2016, 1791, 1624]
    assert sessions[-1].year_start == 2019
    assert sessions[-1].year_end == 2020
    assert sessions[-1].special is False
    assert sessions[-1].session_name == "2019-2020 Session"
```

- [ ] **Step 2: Run to verify it FAILS**

Run: `uv run pytest tests/test_legiscan.py -q -k list_sessions`
Expected: FAIL — `AttributeError: 'LegiScanSource' object has no attribute 'list_sessions'`.

- [ ] **Step 3: Implement.** In `src/zwiadbrain/sources/legiscan.py`, add a `Session` dataclass near `StateLegHistoryInputs` (it already imports `from dataclasses import dataclass`):

```python
@dataclass(frozen=True)
class Session:
    """One LegiScan legislative session (from ``getSessionList``)."""

    session_id: int
    year_start: int
    year_end: int
    special: bool
    session_name: str
```

Then add this method to `LegiScanSource`, immediately after `discover` (and before `change_hashes`):

```python
    def list_sessions(self) -> list[Session]:
        """List the state's legislative sessions (``getSessionList``) newest-first.

        Maps each entry to a :class:`Session`; the prior-years backfill resolves a target
        ``--year`` to the session(s) whose ``[year_start, year_end]`` span covers it
        (PHASE-24/D84).
        """
        payload = self._get("getSessionList", state=self.state)
        sessions: list[Session] = []
        for entry in _items(payload.get("sessions")):
            sid = entry.get("session_id")
            if sid is None:
                continue
            sessions.append(
                Session(
                    session_id=int(sid),
                    year_start=int(entry.get("year_start") or 0),
                    year_end=int(entry.get("year_end") or 0),
                    special=bool(entry.get("special")),
                    session_name=str(entry.get("session_name") or ""),
                )
            )
        return sessions
```

- [ ] **Step 4: Run to verify it PASSES**

Run: `uv run pytest tests/test_legiscan.py -q -k list_sessions`
Expected: PASS.

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py
uv run pyright
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py
git commit -m "feat(legiscan): Session dataclass + list_sessions (getSessionList)"
```

---

### Task 3: `LegiScanSource.list_session_enacted`

**Files:**
- Modify: `src/zwiadbrain/sources/legiscan.py`
- Test: `tests/test_legiscan.py`

`_PASSED_STATUS = 4`, `_opt_str`, `_obj`, `_items`, and `Candidate` are already defined/imported in the module.

- [ ] **Step 1: Write the failing tests**

```python
def test_list_session_enacted_keeps_only_passed_bills() -> None:
    """should keep status==4 rows, carry title+description, skip the session member"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": _fixture("getMasterList.json")})
        cands = _source().list_session_enacted(1624)
    # AB1 (1132030) and AB99 (1132099) are status 4; SB200 (status 6) is excluded.
    assert [c.native_id for c in cands] == ["1132030", "1132099"]
    ab1 = cands[0]
    assert ab1.jurisdiction == "US-CA"
    assert "artificial intelligence" in (ab1.title.lower() + " " + (ab1.summary or "").lower())
    assert ab1.summary is not None  # LegiScan description carried for free recall
    assert ab1.raw.get("change_hash") == "hashA"  # state_cursor reads raw['change_hash']


def test_list_session_enacted_respects_limit() -> None:
    """should cap the returned enacted candidates at limit"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterList": _fixture("getMasterList.json")})
        cands = _source().list_session_enacted(1624, limit=1)
    assert [c.native_id for c in cands] == ["1132030"]
```

- [ ] **Step 2: Run to verify they FAIL**

Run: `uv run pytest tests/test_legiscan.py -q -k list_session_enacted`
Expected: FAIL — no attribute `list_session_enacted`.

- [ ] **Step 3: Implement.** Add to `LegiScanSource` immediately after `list_sessions`:

```python
    def list_session_enacted(
        self, session_id: int, *, limit: int | None = None
    ) -> list[Candidate]:
        """List a session's ENACTED bills (``status == 4``) as candidates (D84, PHASE-24).

        Uses ``getMasterList`` (NOT ``getMasterListRaw`` — the Raw variant carries only
        ``bill_id``/``number``/``change_hash``). Each kept row carries ``title`` and the
        LegiScan ``description`` (onto ``Candidate.summary``) so topic recall is free, plus
        ``change_hash`` in ``raw`` for the state reject-ledger cursor. The numeric-keyed
        ``masterlist`` container's non-bill ``session`` member is skipped by requiring a
        ``bill_id`` (parity with :meth:`change_hashes`).
        """
        masterlist = _obj(self._get("getMasterList", id=session_id).get("masterlist"))
        candidates: list[Candidate] = []
        for entry in masterlist.values():
            row = _obj(entry)
            bill_id = row.get("bill_id")
            if bill_id is None:
                continue
            if int(row.get("status") or 0) != _PASSED_STATUS:
                continue
            candidates.append(
                Candidate(
                    source=self.name,
                    native_id=str(bill_id),
                    jurisdiction=f"US-{self.state.upper()}",
                    title=str(row.get("title") or ""),
                    summary=_opt_str(row.get("description")),
                    update_date=_opt_str(row.get("status_date")),
                    raw={"change_hash": row.get("change_hash"), "status": row.get("status")},
                )
            )
        return candidates[:limit] if limit is not None else candidates
```

- [ ] **Step 4: Run to verify they PASS**

Run: `uv run pytest tests/test_legiscan.py -q -k list_session_enacted`
Expected: PASS (both).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py
uv run pyright
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py
git commit -m "feat(legiscan): list_session_enacted over getMasterList (status==4 only)"
```

---

### Task 4: Extend `keyword_filter` to match title + summary

**Files:**
- Modify: `src/zwiadbrain/pipeline/discover.py` (`keyword_filter`)
- Test: `tests/test_discover.py`

State recall must hit the bill's `description` (carried on `Candidate.summary`), not just the title. Extending `keyword_filter` is safe for federal: federal discovery candidates have `summary=None`, so the haystack is title-only as before.

- [ ] **Step 1: Write the failing test.** Add to `tests/test_discover.py` (read the file first to match its `Candidate` construction style; build candidates with the same fields used by existing tests, adding `summary=`):

```python
def test_keyword_filter_matches_summary_text() -> None:
    """should keep a candidate whose seed appears only in its summary, not its title"""
    from zwiadbrain.pipeline.discover import keyword_filter
    from zwiadbrain.sources.base import Candidate

    title_miss = Candidate(
        source="legiscan", native_id="1", jurisdiction="US-CA",
        title="An act relating to public works.",
        summary="Establishes an artificial intelligence oversight board.",
    )
    no_match = Candidate(
        source="legiscan", native_id="2", jurisdiction="US-CA",
        title="An act relating to fishing licenses.",
        summary="Concerns recreational fishing fees.",
    )
    kept = keyword_filter([title_miss, no_match], ["artificial intelligence"])
    assert [c.native_id for c in kept] == ["1"]


def test_keyword_filter_title_only_when_summary_absent() -> None:
    """should preserve title-only matching for candidates with no summary (federal)"""
    from zwiadbrain.pipeline.discover import keyword_filter
    from zwiadbrain.sources.base import Candidate

    fed = Candidate(source="congress", native_id="118/hr/1", jurisdiction="US",
                    title="Artificial Intelligence Accountability Act")
    other = Candidate(source="congress", native_id="118/hr/2", jurisdiction="US",
                      title="Farm Bill")
    kept = keyword_filter([fed, other], ["artificial intelligence"])
    assert [c.native_id for c in kept] == ["118/hr/1"]
```

- [ ] **Step 2: Run to verify the new summary test FAILS (title-only test already passes)**

Run: `uv run pytest tests/test_discover.py -q -k keyword_filter`
Expected: `test_keyword_filter_matches_summary_text` FAILS (summary not consulted yet); the title-only test passes.

- [ ] **Step 3: Implement.** In `src/zwiadbrain/pipeline/discover.py`, change `keyword_filter` to match against title + summary:

```python
def keyword_filter(candidates: list[Candidate], seeds: list[str] | None) -> list[Candidate]:
    """Keep candidates whose title OR summary contains any seed (case-insensitive).

    Absent or empty ``seeds`` means "no filter" — every candidate passes. The summary is
    consulted so state discovery (which carries the LegiScan ``description`` on
    ``Candidate.summary``) recalls on the bill text; federal candidates have no summary, so
    matching is title-only for them, unchanged.
    """
    if not seeds:
        return candidates
    lowered = [seed.lower() for seed in seeds]
    return [
        c
        for c in candidates
        if any(seed in f"{c.title} {c.summary or ''}".lower() for seed in lowered)
    ]
```

- [ ] **Step 4: Run to verify BOTH new tests PASS and the existing discover suite is green**

Run: `uv run pytest tests/test_discover.py -q`
Expected: PASS (all — including the existing `keyword_filter`/`recall_filter` tests, which use title-only candidates).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check src/zwiadbrain/pipeline/discover.py tests/test_discover.py
uv run pyright
git add src/zwiadbrain/pipeline/discover.py tests/test_discover.py
git commit -m "feat(discover): keyword_filter matches title+summary (enables state recall)"
```

---

### Task 5: `fetch-state-enacted-candidates` CLI command

**Files:**
- Modify: `src/zwiadbrain/cli.py` (add command after `fetch_state_candidates`, ~line 588; add one line to the module docstring command list)
- Test: `tests/test_cli.py`

Reuses (already imported in `cli.py`): `keyword_filter`, `enrich`, `stage_json`, `load_reference`, `load_reject_ledger`, `filter_by_key`, `filter_cached_rejects`, `state_key`, `state_cursor`, `_existing_state_bill_ids`, `LegiScanSource`, `_DEFAULT_TOPICS`. New import needed: `Session` is internal to legiscan; the command only uses `list_sessions()`/`list_session_enacted()` on the source, so no new import beyond what exists.

- [ ] **Step 1: Write the failing tests.** Add to `tests/test_cli.py` after the `fetch_state_candidates` tests. The LegiScan base URL has no per-op path, so route by op with the existing helper pattern (check how `test_legiscan`/`test_cli` route LegiScan ops; if `test_cli.py` lacks a LegiScan `_route_by_op`, define a local handler that dispatches on the `op` query param). Enrich is stubbed via monkeypatch to avoid getBill fixtures.

```python
def _fake_state_enrich(source: object, candidate: Candidate) -> Bill:
    """Stub enrich: build a state Bill from the candidate (no HTTP)."""
    return Bill(
        id=f"ca-2019-{candidate.native_id}",
        jurisdiction=candidate.jurisdiction,
        title=candidate.title or "x",
        bill_number=candidate.native_id,
        enacted=True,
        legiscan_bill_id=int(candidate.native_id),
    )


def _route_legiscan(mock: respx.MockRouter, mapping: dict[str, dict[str, Any]]) -> None:
    """Dispatch LegiScan ops (single base URL) to fixture payloads by the `op` query param."""
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op")
        return httpx.Response(200, json=mapping[op])
    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


def test_fetch_state_enacted_keeps_topical_enacted_laws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should resolve --year to a session, keep enacted+topical bills, stage them"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    # AB1 (status 4, AI title) kept; AB99 (status 4, off-topic) dropped by recall;
    # SB200 (privacy but status 6 failed) excluded by the enacted filter.
    assert [b["legiscan_bill_id"] for b in data] == [1132030]


def test_fetch_state_enacted_classify_all_stages_all_enacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--classify-all stages every enacted (status==4) bill, skipping recall"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019",
             "--classify-all", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["legiscan_bill_id"] for b in data] == [1132030, 1132099]  # both enacted, no recall


def test_fetch_state_enacted_errors_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when LEGISCAN_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    result = runner.invoke(
        app, ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019"]
    )
    assert result.exit_code == 1
    assert "LEGISCAN_API_KEY" in result.output
```

Add near the top of `tests/test_cli.py` (with the other imports/helpers) a LegiScan fixture loader if one doesn't already exist:

```python
_LEGISCAN_FIX = Path(__file__).parent / "fixtures" / "legiscan"


def _legiscan_fixture(name: str) -> dict[str, Any]:
    return json.loads((_LEGISCAN_FIX / name).read_text(encoding="utf-8"))
```

Also confirm `LEGISCAN_API_BASE` is imported in `tests/test_cli.py` (`from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE`); add it if missing. `Any` and `httpx` are needed by `_route_legiscan` — confirm they're imported.

- [ ] **Step 2: Run to verify they FAIL**

Run: `uv run pytest tests/test_cli.py -q -k fetch_state_enacted`
Expected: FAIL — `No such command 'fetch-state-enacted-candidates'`.

- [ ] **Step 3: Implement.** In `src/zwiadbrain/cli.py`, add after `fetch_state_candidates` (before `fetch-bill`):

```python
@app.command(name="fetch-state-enacted-candidates")
def fetch_state_enacted_candidates(
    state: Annotated[str, typer.Option(help="Two-letter state, e.g. ca.")],
    year: Annotated[int, typer.Option(help="Target year; resolves to the session(s) covering it.")],
    limit: Annotated[
        int, typer.Option(min=1, help="Max in-scope candidates to stage (recall output cap).")
    ] = 250,
    classify_all: Annotated[
        bool,
        typer.Option(
            "--classify-all/--no-classify-all",
            help="Skip the recall pre-filter; stage every enacted bill for classification.",
        ),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop bills already tracked or in the state reject ledger.",
        ),
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
) -> None:
    """Fetch a state session's ENACTED bills and stage the in-scope ones for classification.

    Enacted-first discovery half of ``/zwiad-backfill-enacted-state`` (D84): ``getSessionList``
    resolves ``--year`` to the session(s) covering it, then ``getMasterList`` lists that
    session's bills and we keep only ``status == 4 (Passed)`` — non-enacted bills never enter
    the pipeline. By default a free title+description keyword recall keeps the topically-
    relevant enacted bills and the classifier subagent gates the survivors; ``--classify-all``
    skips recall and stages every enacted bill.
    """
    try:
        api_key = load_settings().require_legiscan_api_key()
        source = LegiScanSource(api_key, state)
        sessions = [s for s in source.list_sessions() if s.year_start <= year <= s.year_end]
        if not sessions:
            raise ConfigError(f"no {state} session covers year {year}")
        enacted: list[Candidate] = []
        for session in sessions:
            enacted.extend(source.list_session_enacted(session.session_id))
        if classify_all:
            candidates = enacted
        else:
            seeds = load_reference(topics).seeds
            candidates = keyword_filter(enacted, seeds)
        if skip_existing:
            known = _existing_state_bill_ids(wiki, state)
            ledger = load_reject_ledger(wiki / ".rejects" / "state.json")
            before = len(candidates)
            candidates = filter_by_key(candidates, known, key_of=state_key)
            after_unseen = len(candidates)
            candidates = filter_cached_rejects(
                candidates, ledger, key_of=state_key, cursor_of=state_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(candidates)} cached-reject of {before} enacted"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        candidates = candidates[:limit]
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} enacted {state} candidate(s) to {path}")
```

`ConfigError` is already imported in `cli.py` (from `zwiadbrain.exceptions`). Verify before relying on it; if not, add it to that import.

- [ ] **Step 4: Run to verify the new tests PASS**

Run: `uv run pytest tests/test_cli.py -q -k fetch_state_enacted`
Expected: PASS (all three).

- [ ] **Step 5: Add a line to the module docstring command list** in `cli.py` (after the `fetch-enacted-candidates`/`fetch-state-candidates` lines):

```
- ``fetch-state-enacted-candidates`` — enacted-only state discovery for ``/zwiad-backfill-enacted-state`` (D84).
```

- [ ] **Step 6: Authoritative gate + commit**

```bash
uv run ruff check .
uv run pyright
uv run pytest -q
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(backfill): fetch-state-enacted-candidates CLI (enacted state discovery, D84)"
```

---

### Task 6: Full gate + live smoke + ARCHITECTURE note

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Full authoritative gate**

Run: `uv run ruff check . && uv run pyright && uv run pytest -q`
Expected: PASS; prior suite + the new PHASE-24 tests green. Fix anything introduced.

- [ ] **Step 2: Live smoke (gated; `.env` key + egress).** Use `--classify-all` with a small `--limit` to keep it cheap (recall is unit-tested offline); this exercises `getSessionList` → `getMasterList` → enrich end-to-end against the real API:

```bash
uv run zwiadbrain fetch-state-enacted-candidates --state ca --year 2019 --classify-all --limit 5 --out data/runs/smoke-ca-2019
```
Expected: exit 0, prints `fetched N enacted ca candidate(s) …`; verify the staged bills all have `"enacted": true` and `jurisdiction: "US-CA"`. `data/runs/` is gitignored — do not commit it. Reconcile against Task 1 if the shape differs.

- [ ] **Step 3: ARCHITECTURE note.** Add a short line near the `/zwiad-scan-states` bullet noting `fetch-state-enacted-candidates` is the enacted-only state discovery half (LegiScan `getMasterList`, `status==4`) backing the planned `/zwiad-backfill-enacted-state` (PHASE-24/D84), distinct from the routine `fetch-state-candidates`.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs(backfill): note fetch-state-enacted-candidates in ARCHITECTURE (PHASE-24)"
```

---

## Self-Review

**Spec coverage (PHASE-24 / §4.2, §4.3, §4.4 state half):**
- §4.2 `list_sessions` (getSessionList) → Task 2 ✓; `list_session_enacted` over **`getMasterList`** filtering `status==4`, carrying title+description+change_hash → Task 3 ✓.
- §4.3 `fetch-state-enacted-candidates --state --year [--limit --classify-all --skip-existing --out --wiki]` → Task 5 ✓.
- §4.4 free title+description recall (state) → Task 4 (keyword_filter extension) + Task 5 (default recall via keyword_filter; `--classify-all` bypass) ✓.
- §5 state `--skip-existing` parity (reject ledger, `state_key`/`state_cursor`) → Task 5 ✓.
- §7 enacted definition (status==4; failed/vetoed excluded) → Task 3 + the SB200 fixture case ✓.
- §10 tests (list_sessions, list_session_enacted mixed-status, CLI happy/classify-all/no-key) → Tasks 2,3,5 ✓.
- Live-validation (§4.2, §15 resolution) → Task 1 Step 3 + Task 6 Step 2 ✓.
- *Deferred to later phases:* orchestration/slash command/tracker/D84-D85 (PHASE-25); the run (PHASE-26). The post-enrich non-law (ceremonial resolution) guard from the original phase file is **not needed** — `status==4` already excludes non-passed items, and resolutions that are chaptered are genuine enactments; no separate guard is built (noted here so its omission is intentional, not forgotten).

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands show expected output.

**Type/name consistency:** `Session(session_id, year_start, year_end, special, session_name)` defined Task 2, used in Task 5's `s.year_start <= year <= s.year_end`. `list_session_enacted(session_id, *, limit=None)` defined Task 3, called in Task 5 as `list_session_enacted(session.session_id)`. `keyword_filter(candidates, seeds)` signature unchanged (Task 4 changes body only) — callers unaffected. `state_key`=native_id and `state_cursor`=`raw['change_hash']` matched by Task 3's Candidate (native_id=str(bill_id), raw={'change_hash':…}). `_fake_state_enrich(source, candidate)` matches `enrich(source, candidate)` arity.

**Open reconciliation:** Task 1 Step 3 (live shape) and Task 6 Step 2 (live smoke) are the only reality-divergence points; both instruct reconciliation against the live response.
