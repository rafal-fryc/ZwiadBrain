# PHASE-23 — Federal enacted discovery (`/law/{congress}`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add enacted-only federal discovery — a `CongressSource.discover_laws()` over Congress.gov `/law/{congress}/pub` plus a `fetch-enacted-candidates` CLI command — so the prior-years backfill never enriches a non-enacted bill.

**Architecture:** `/law/{congress}/pub` returns *only* enacted public laws, in the same item shape as the existing `/bill` list, so we reuse `_to_candidate` + the page-sweep loop (extracted to a shared `_sweep_candidates`). The CLI half mirrors `fetch-candidates`: discover → two-stage `recall_filter` (default) → `enrich` survivors → `stage_json`. `--classify-all` skips recall; `--skip-existing` reuses the federal reject ledger.

**Tech Stack:** Python 3.12, typer, httpx, respx (test mocks), pytest, pydantic. Implements PHASE-23 of `docs/superpowers/specs/2026-06-08-enacted-laws-backfill-design.md` (the federal half of D84).

**Phase mapping:** spec PHASE-A = repo PHASE-23 (next after PHASE-22).

**Run all commands from repo root** `C:\Users\rafst\documents\projectas\zwiadbrain`. Tests run with `uv run pytest`; the quality gate is `uv run ruff check . && uv run pyright && uv run pytest -q` (match whatever the repo's existing gate is — see `pyproject.toml`).

---

### Task 1: Discovery fixture + live shape confirmation

**Files:**
- Create: `tests/fixtures/congress/law_list.json`

The `/law/{congress}/pub` response shares the `/bill` list shape (a `bills` array + `pagination.count`), each item carrying `congress`, `type`, `number`, `title`, `updateDate`/`updateDateIncludingText`, and a `laws` array. This fixture has two entries: one whose title matches an AI seed (recall Stage 1 keeps it) and one that doesn't (forces a Stage-2 policyArea probe downstream).

- [ ] **Step 1: Write the fixture**

```json
{
  "bills": [
    {
      "congress": 118,
      "type": "HR",
      "number": "8818",
      "title": "Artificial Intelligence Accountability Act",
      "originChamber": "House",
      "updateDate": "2024-12-21T03:27:05Z",
      "updateDateIncludingText": "2024-12-21T03:27:05Z",
      "laws": [{"number": "118-99", "type": "Public Law"}],
      "latestAction": {"actionDate": "2024-12-20", "text": "Became Public Law No: 118-99."},
      "url": "https://api.congress.gov/v3/bill/118/hr/8818?format=json"
    },
    {
      "congress": 118,
      "type": "S",
      "number": "2073",
      "title": "FAA Reauthorization Act of 2024",
      "originChamber": "Senate",
      "updateDate": "2024-05-14T08:01:00Z",
      "updateDateIncludingText": "2024-05-14T08:01:00Z",
      "laws": [{"number": "118-63", "type": "Public Law"}],
      "latestAction": {"actionDate": "2024-05-13", "text": "Became Public Law No: 118-63."},
      "url": "https://api.congress.gov/v3/bill/118/s/2073?format=json"
    }
  ],
  "pagination": {"count": 2}
}
```

- [ ] **Step 2: Confirm the real shape live (one-shot, gated)**

The `.env` has `CONGRESS_API_KEY`. Probe the real endpoint once and compare field names to the fixture:

```bash
uv run python -c "import os,httpx,json; from dotenv import load_dotenv; load_dotenv(); k=os.environ['CONGRESS_API_KEY']; r=httpx.get('https://api.congress.gov/v3/law/118/pub', params={'api_key':k,'format':'json','limit':2}); d=r.json(); print(json.dumps({'keys':list(d.keys()),'first':d.get('bills',[{}])[0]}, indent=2)[:1500])"
```

Expected: top-level `bills` + `pagination`; each item has `congress`, `type`, `number`, `title`, `updateDate`/`updateDateIncludingText`, `laws`.
**If the real shape differs** (different container key, missing `laws`, different sort behaviour), update `law_list.json` to match the real response and note the delta in the commit message — every later task reads field names from this fixture.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/congress/law_list.json
git commit -m "test(backfill): /law/{congress}/pub discovery fixture for enacted federal laws"
```

---

### Task 2: Extract the shared page-sweep helper (refactor, no behavior change)

**Files:**
- Modify: `src/zwiadbrain/sources/congress.py` (`discover`, ~lines 300–360)
- Test: `tests/test_congress.py` (existing discovery tests guard this)

`discover_laws` needs the same offset-sweep/dedup/truncation loop as `discover`. Extract it to a private `_sweep_candidates(path, ...)` so both call it (DRY). This is a pure mechanical extraction — the existing `discover` tests prove no regression.

- [ ] **Step 1: Run the existing discovery tests to confirm green baseline**

Run: `uv run pytest tests/test_congress.py -q -k discover`
Expected: PASS (all current discovery tests).

- [ ] **Step 2: Add `_sweep_candidates` and make `discover` delegate to it**

Replace the body of `discover` (the loop) with a call to a new helper. The helper is the existing loop verbatim, parameterized by `path`:

```python
    def discover(
        self,
        *,
        congress: int | None = None,
        since: dt.datetime | None = None,
        limit: int = 20,
        max_pages: int = 1,
    ) -> list[Candidate]:
        """List bills (newest-updated first) as candidates.

        With ``congress`` set, lists that congress; otherwise lists across congresses.
        ``limit`` (≤ 250) is the per-page size. ``max_pages`` bounds an OPT-IN back-catalog
        offset sweep (PHASE-22/D81); the default ``1`` preserves single-request behaviour.
        """
        path = f"/bill/{congress}" if congress is not None else "/bill"
        return self._sweep_candidates(path, since=since, limit=limit, max_pages=max_pages)

    def _sweep_candidates(
        self,
        path: str,
        *,
        since: dt.datetime | None,
        limit: int,
        max_pages: int,
    ) -> list[Candidate]:
        """Offset-paginate ``path`` (a ``{"bills": [...]}`` list endpoint) into candidates.

        Shared by ``discover`` (``/bill``) and ``discover_laws`` (``/law/.../pub``). Default
        ``max_pages=1`` omits ``offset`` so the single-request behaviour is unchanged; with
        ``max_pages>1`` successive offsets are accumulated, de-duped by ``native_id``, and a
        truncated remainder (server total > collected) is logged, never silently dropped.
        """
        page_size = min(max(limit, 1), 250)
        pages = max(max_pages, 1)
        collected: list[Candidate] = []
        seen: set[str] = set()
        total: int | None = None
        offset = 0
        for _ in range(pages):
            params: dict[str, str | int] = {"sort": "updateDate desc", "limit": page_size}
            if offset:  # omit offset on the first page so the single-page request is unchanged
                params["offset"] = offset
            if since is not None:
                params["fromDateTime"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            payload = self._get_json(path, **params)
            bills = _items(payload.get("bills"))[:page_size]
            if total is None:
                count = _obj(payload.get("pagination")).get("count")
                total = count if isinstance(count, int) else None
            for bill in bills:
                candidate = self._to_candidate(bill)
                if candidate.native_id in seen:
                    continue
                seen.add(candidate.native_id)
                collected.append(candidate)
            offset += page_size
            if not bills or len(bills) < page_size:
                break
            if total is not None and offset >= total:
                break
        if isinstance(total, int) and total > len(collected):
            _LOGGER.warning(
                "discovery truncated: returned %d of %d reported bills for %s (max_pages=%d)",
                len(collected), total, path, pages,
            )
        return collected
```

- [ ] **Step 3: Run the discovery tests to verify no regression**

Run: `uv run pytest tests/test_congress.py -q -k discover`
Expected: PASS (identical behaviour — only structure changed).

- [ ] **Step 4: Commit**

```bash
git add src/zwiadbrain/sources/congress.py
git commit -m "refactor(congress): extract _sweep_candidates from discover (no behavior change)"
```

---

### Task 3: `CongressSource.discover_laws`

**Files:**
- Modify: `src/zwiadbrain/sources/congress.py` (add method after `discover`)
- Test: `tests/test_congress.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_congress.py` (after the discovery tests):

```python
def test_discover_laws_lists_enacted_public_laws_as_candidates() -> None:
    """should list /law/{congress}/pub entries as congress/type/number candidates"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        candidates = _source().discover_laws(118, limit=10)
    assert [c.native_id for c in candidates] == ["118/hr/8818", "118/s/2073"]
    assert candidates[0].jurisdiction == "US"
    assert candidates[0].title == "Artificial Intelligence Accountability Act"


def test_discover_laws_respects_limit() -> None:
    """should return no more candidates than the requested per-page limit"""
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        candidates = _source().discover_laws(118, limit=1)
    assert len(candidates) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_congress.py -q -k discover_laws`
Expected: FAIL with `AttributeError: 'CongressSource' object has no attribute 'discover_laws'`.

- [ ] **Step 3: Add `discover_laws`**

In `src/zwiadbrain/sources/congress.py`, immediately after `discover` (and before `_to_candidate`):

```python
    def discover_laws(
        self, congress: int, *, limit: int = 250, max_pages: int = 1
    ) -> list[Candidate]:
        """List a congress's ENACTED public laws as candidates (D84, PHASE-23).

        Hits ``/law/{congress}/pub`` — Congress.gov's enacted public-law list — so the
        candidate set is enacted-only *by construction*; no non-enacted bill enters the
        pipeline. Items share the ``/bill`` list shape, so ``_to_candidate`` maps them to the
        same ``congress/type/number`` ``native_id`` that ``fetch()`` consumes. Pagination,
        de-dup, and truncation logging match ``discover`` (shared ``_sweep_candidates``).
        """
        return self._sweep_candidates(
            f"/law/{congress}/pub", since=None, limit=limit, max_pages=max_pages
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_congress.py -q -k discover_laws`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/sources/congress.py tests/test_congress.py
git commit -m "feat(congress): discover_laws over /law/{congress}/pub (enacted-only)"
```

---

### Task 4: `fetch-enacted-candidates` CLI command

**Files:**
- Modify: `src/zwiadbrain/cli.py` (add command next to `fetch-candidates`, ~line 326; update module docstring list ~line 9)
- Test: `tests/test_cli.py`

Mirrors `fetch-candidates`: discover enacted → recall (default) → enrich survivors → stage. Reuses `_existing_federal_bill_ids`, `filter_unseen`, `filter_cached_rejects`, `federal_key`, `federal_cursor`, `load_reject_ledger`, `recall_filter`, `enrich`, `stage_json`, `load_reference`, `_DEFAULT_TOPICS`, `_SCAN_LIMIT` — all already imported in `cli.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (after the `fetch_candidates` tests). The first does a real enrich on the survivor (reusing `_route_backfill`'s `/bill/118/hr/8818` routes); the rest monkeypatch `cli.enrich` to a stub so recall/flags can be asserted without per-bill fixtures.

```python
def test_fetch_enacted_keeps_only_topical_enacted_laws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should discover /law/{congress}/pub, recall-filter, and enrich only survivors"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        # S.2073 has no title seed -> Stage-2 probe; reply with a policyArea NOT in the allowlist.
        mock.get("/bill/118/s/2073").respond(
            json={"bill": {"policyArea": {"name": "Transportation and Public Works"}}}
        )
        _route_backfill(mock)  # enrich routes for the survivor 118/hr/8818
        result = runner.invoke(
            app, ["fetch-enacted-candidates", "--congress", "118", "--out", str(out)]
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in data] == ["118-hr-8818"]
    bill = Bill.model_validate(data[0])
    assert bill.enacted is True
    assert bill.public_law == "118-99"


def _fake_enrich(source: object, candidate: Candidate) -> Bill:
    """Stub enrich: build a Bill straight from the candidate (no HTTP)."""
    cong, btype, num = candidate.native_id.split("/")
    return Bill(
        id=f"{cong}-{btype}-{num}",
        jurisdiction="US",
        title=candidate.title or "x",
        bill_number=f"{btype.upper()} {num}",
        enacted=True,
    )


def test_fetch_enacted_classify_all_skips_recall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--classify-all stages every enacted law and makes no policyArea probe"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        law = mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        probe = mock.get("/bill/118/s/2073").respond(json={"bill": {}})
        result = runner.invoke(
            app,
            ["fetch-enacted-candidates", "--congress", "118", "--classify-all", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in data] == ["118-hr-8818", "118-s-2073"]
    assert law.called and not probe.called  # no Stage-2 probe under --classify-all


def test_fetch_enacted_skip_existing_drops_tracked_law(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--skip-existing drops an enacted law that already has a wiki page"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    wiki = tmp_path / "wiki"
    write_page(
        Bill(id="118-hr-8818", jurisdiction="US", title="AI Act", bill_number="H.R. 8818"), wiki
    )
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        mock.get("/bill/118/s/2073").respond(
            json={"bill": {"policyArea": {"name": "Transportation and Public Works"}}}
        )
        result = runner.invoke(
            app,
            [
                "fetch-enacted-candidates", "--congress", "118",
                "--skip-existing", "--wiki", str(wiki), "--out", str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert data == []  # the only topical enacted law was already tracked


def test_fetch_enacted_errors_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when CONGRESS_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    result = runner.invoke(app, ["fetch-enacted-candidates", "--congress", "118"])
    assert result.exit_code == 1
    assert "CONGRESS_API_KEY" in result.output
```

Note: confirm `Candidate` is imported in `tests/test_cli.py`; if not, add `from zwiadbrain.sources.base import Candidate` to the imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -q -k fetch_enacted`
Expected: FAIL — `No such command 'fetch-enacted-candidates'` / non-zero exit.

- [ ] **Step 3: Implement the command**

In `src/zwiadbrain/cli.py`, add immediately after the `fetch_candidates` function (before `render-classified`):

```python
@app.command(name="fetch-enacted-candidates")
def fetch_enacted_candidates(
    congress: Annotated[int, typer.Option(min=1, help="Congress number, e.g. 118.")],
    limit: Annotated[
        int, typer.Option(min=1, help="Max in-scope candidates to stage (recall output cap).")
    ] = 250,
    max_pages: Annotated[
        int,
        typer.Option(min=1, help="Pages of the enacted-law list to sweep (covers a full congress)."),
    ] = 5,
    classify_all: Annotated[
        bool,
        typer.Option(
            "--classify-all/--no-classify-all",
            help="Skip the recall pre-filter; stage every enacted law for classification.",
        ),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop enacted laws already tracked or in the reject ledger.",
        ),
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
) -> None:
    """Fetch a congress's ENACTED public laws and stage the in-scope ones for classification.

    Enacted-first discovery half of ``/zwiad-backfill-enacted`` (D84): ``/law/{congress}/pub``
    lists only enacted public laws, so non-enacted bills never enter the pipeline. By default
    the two-stage ``recall_filter`` (title seeds + ``policyArea`` probe over the *whole* enacted
    set) keeps the topically-relevant laws and the classifier subagent gates the survivors.
    ``--classify-all`` skips recall and stages every enacted law (zero recall risk, ~6x more
    enrichment + classifier work).
    """
    try:
        reference = load_reference(topics)
        seeds, policy_areas = reference.seeds, reference.policy_areas
        api_key = load_settings().require_congress_api_key()
        source = CongressSource(api_key)
        scanned = source.discover_laws(congress, limit=_SCAN_LIMIT, max_pages=max_pages)
        if skip_existing:
            known = _existing_federal_bill_ids(wiki)
            ledger = load_reject_ledger(wiki / ".rejects" / "federal.json")
            before = len(scanned)
            scanned = filter_unseen(scanned, known)
            after_unseen = len(scanned)
            scanned = filter_cached_rejects(
                scanned, ledger, key_of=federal_key, cursor_of=federal_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(scanned)} cached-reject of {before} enacted laws"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        if classify_all:
            candidates = scanned[:limit]
        else:
            candidates = recall_filter(
                scanned,
                source,
                seeds=seeds,
                policy_areas=policy_areas,
                limit=limit,
                max_probe=len(scanned),  # probe the WHOLE enacted set — recall not truncated
            )
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} enacted candidate(s) to {path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q -k fetch_enacted`
Expected: PASS (all four tests).

- [ ] **Step 5: Update the module docstring command list**

In `src/zwiadbrain/cli.py`, add a line under the command list (~line 9), after the `fetch-candidates` line:

```
- ``fetch-enacted-candidates`` — enacted-only federal discovery for ``/zwiad-backfill-enacted`` (D84).
```

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(backfill): fetch-enacted-candidates CLI (enacted federal discovery, D84)"
```

---

### Task 5: Full gate + live smoke + docs note

**Files:**
- Modify: `ARCHITECTURE.md` (command list, ~line 42 near `/zwiad-backfill`)

- [ ] **Step 1: Run the full quality gate**

Run: `uv run ruff check . && uv run pyright && uv run pytest -q`
Expected: PASS, with the new tests included and the prior suite (79+ tests) still green. Fix any lint/type error before continuing (e.g. unused import, missing return annotation).

- [ ] **Step 2: Live smoke against a real Congress (gated; needs `.env` key + egress)**

```bash
uv run zwiadbrain fetch-enacted-candidates --congress 118 --limit 8 --out data/runs/smoke-118
```
Expected: exits 0, prints `fetched N enacted candidate(s) to data/runs/smoke-118/...`; the staged bills all have `"enacted": true`. `data/runs/` is gitignored — do not commit it. If it errors on the endpoint shape, reconcile against Task 1's findings.

- [ ] **Step 3: Add the command to ARCHITECTURE.md**

Under the slash-command / CLI notes, add a short line noting `fetch-enacted-candidates` is the enacted-only federal discovery half backing `/zwiad-backfill-enacted` (PHASE-23/D84), distinct from the routine `fetch-candidates`.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs(backfill): note fetch-enacted-candidates in ARCHITECTURE (PHASE-23)"
```

---

## Self-Review

**Spec coverage (PHASE-23 / §4.1, §4.3, §4.4 federal half):**
- §4.1 `discover_laws` over `/law/{congress}/pub` → Task 3. ✓
- §4.3 `fetch-enacted-candidates` CLI (`--limit`, `--max-pages`, `--skip-existing`, `--classify-all`, `--out`, `--wiki`) → Task 4. ✓
- §4.4 recall-default (two-stage, `max_probe` = full set) + `--classify-all` opt-in → Task 4 Step 3 + tests. ✓
- §5 reuse of `enrich`/`stage_json`/reject-ledger filters → Task 4 (imports already present). ✓
- §10 test plan (discover_laws, CLI happy/skip-existing/no-key, fixture) → Tasks 1, 3, 4. ✓
- Live-validation gate (§4.1, §15) → Task 1 Step 2 + Task 5 Step 2. ✓
- *Deferred to later phases (correctly out of PHASE-23 scope):* state discovery (PHASE-24), slash command + tracker + DECISIONS entry (PHASE-25), the run itself (PHASE-26).

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command shows expected output. ✓

**Type/name consistency:** `_sweep_candidates(path, *, since, limit, max_pages)` defined in Task 2 and called identically in Tasks 2 & 3. `discover_laws(congress, *, limit, max_pages)` defined in Task 3, called in Task 4 as `discover_laws(congress, limit=_SCAN_LIMIT, max_pages=max_pages)`. ✓ `recall_filter(..., limit=, max_probe=)` matches `discover.py` signature. ✓ `_fake_enrich(source, candidate)` matches `enrich(source, candidate)` arity. ✓ Reused symbols (`_existing_federal_bill_ids`, `filter_unseen`, `filter_cached_rejects`, `federal_key`, `federal_cursor`, `load_reject_ledger`, `stage_json`, `load_reference`, `_SCAN_LIMIT`, `_DEFAULT_TOPICS`) all verified imported in `cli.py`. ✓

**Open reconciliation:** Task 1 Step 2 is the only place reality can diverge from the plan (the `/law/{congress}/pub` shape); it explicitly instructs reconciliation, and Task 5 Step 2 re-checks live.
