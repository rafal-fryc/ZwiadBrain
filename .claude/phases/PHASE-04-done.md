# Phase 04 — LLM agents (relevance classifier, summarizer, amendment-explainer)
Status: DONE

## Outcome (2026-05-27)
Built and gated green (89 pytest, ruff, pyright strict): `topics.yaml`, `reference/loader.py`, the three
`.claude/agents/*.md` subagents, `.claude/commands/zwiad-backfill.md`, the `fetch-candidates` +
`render-classified` CLI commands, `anthropic` dependency dropped, `data/runs/` gitignored, DECISIONS #26–32.
**UAT PASSED** (`/zwiad-backfill 118 50`, live data, regular plan usage): two AI bills classified in,
summarized, and rendered; Insurance Data Protection Act and SAFER Banking Act correctly classified out;
the classifier drew the nuanced "core data-privacy = in, incidental financial data = out" line on real
bills (decision 32 confirms financial-privacy is in scope). Discovery-recall gap surfaced during UAT is
tracked separately in PHASE-03.1. Duplicate-timeline-action rows fixed (separate `fix(congress)` commit).

## Goal
Add the Claude-powered relevance gate (with an explicit DISQUALIFY rubric, decision 17) plus a bill summarizer and amendment-explainer — implemented as **Claude Code subagents driven by an interactive session** so they run on the user's **regular plan usage** — with Python providing deterministic fetch/render tooling and file-based JSON handoffs.

## LLM mechanism (settled — interactive Claude Code, regular plan usage)
The orchestrator is **Claude Code itself**, running in a terminal the user keeps open. A slash command coordinates the run; the three LLM tasks are `.claude/agents/*.md` subagents dispatched via the Task tool **within the interactive session** — which draws the user's **regular plan usage limits**, NOT the separate Agent SDK credit pool that `claude -p`/the SDK use from June 15, 2026 (and NOT a metered API key). Python never calls an LLM. Python and Claude Code hand off via gitignored JSON files under `data/runs/<run-id>/` (mirrors the sibling `Zwiad` project's file-based agent communication).

## Flow (`/zwiad-backfill congress=118 limit=5` in an open session)
1. Claude Code runs `python -m zwiadbrain fetch-candidates …` → discover → `keyword_filter` (seeds from `topics.yaml`) → `source.fetch` → write enriched `Bill`s to `data/runs/<id>/candidates.json`.
2. Claude Code loops candidates: dispatch **`classifier`** subagent per bill (title + CRS summary) → `{in_scope, topics, confidence, rationale, criterion}`. For in-scope bills, dispatch **`summarizer`** (→ summary) and **`amendment-explainer`** (→ per-amendment `what_changed`). Apply `topics`/`summary`/`what_changed`; out-of-scope bills dropped.
3. Claude Code writes in-scope enriched `Bill`s to `data/runs/<id>/classified.json` → runs `python -m zwiadbrain render-classified …` → validate `topics ⊆ topic_keys`, render pages, update index. Reports rendered N, out-of-scope M.

## Architectural note (approved pivot — reaches beyond Phase 04)
This flips the orchestration model the PLAN assumed (Python-orchestrated + cron + `claude -p`). Consequences to revisit in their own phases, NOT here: **PHASE-06** (`run.py` two-pass) becomes a slash command; **PHASE-10** (cron + `claude -p`) no longer fits — scheduling moves in-session (`/loop` or a scheduled task in the open terminal). The committed-wiki product, models, Congress source, renderer, and FTS5 index from phases 1–3 are unaffected.

## Tasks
- [ ] `reference/topics.yaml` — AI/privacy/cyber taxonomy, keyword seed lexicon, positive criteria, and DISQUALIFY lexicon (single source for both the Python recall seeds and the classifier subagent's rubric)
- [ ] `reference/loader.py` — `load_reference(path) -> Reference` exposing `seeds` (flat, deduped → feeds `keyword_filter`) and `topic_keys` (valid `topics[]` values → validated at render). (No LLM prompt-block rendering needed in Python; the classifier subagent reads `topics.yaml` directly.)
- [ ] `.claude/agents/classifier.md` — subagent. Frontmatter: `model: haiku`, `tools: Read` (to read `reference/topics.yaml`), low maxTurns. Body: role + DISQUALIFY-rubric instructions + strict-JSON output contract `{in_scope, topics, confidence, rationale, criterion}`; topics must come from the taxonomy keys; must cite the satisfied positive criterion (in-scope) or surviving disqualifier (borderline).
- [ ] `.claude/agents/summarizer.md` — subagent. `model: sonnet`, `tools: Read`. Body: plain-language bill summary from the bill data passed inline.
- [ ] `.claude/agents/amendment-explainer.md` — subagent. `model: sonnet`, `tools: Read`. Body: one call per bill; returns `{amendment_number: what_changed}` JSON for all amendments.
- [ ] `.claude/commands/zwiad-backfill.md` — slash command orchestrating the Flow above (fetch-candidates → per-bill subagent dispatch + gating → render-classified). Documents the staging-file contract.
- [ ] `cli.py` `fetch-candidates` — `--congress N --limit K [--seed ...] [--out DIR]`; discover + keyword_filter (seeds default from `topics.yaml`) + fetch; write `candidates.json` (list of enriched `Bill`s) to `data/runs/<id>/`.
- [ ] `cli.py` `render-classified` — `--in FILE [--wiki PATH] [--db PATH]`; read in-scope enriched `Bill`s, validate `topics ⊆ topic_keys`, render pages, update index; report counts.
- [ ] `cli.py` `backfill` — leave as the deterministic, no-LLM command (discover→fetch→render, CRS summary, no gate). Still useful and fully testable.
- [ ] staging — `data/runs/<id>/` is gitignored (extend `.gitignore` if not already covered by `data/`); a small pydantic wrapper for the run manifest if helpful.
- [ ] `pyproject.toml` — **remove `anthropic`** (unused); no new runtime dependency.
- [ ] `exceptions.py` — only what the new Python commands need (e.g. a staging/IO error); no LLM-client errors (Python makes no LLM calls).
- [ ] `DECISIONS.md` — log the decisions below (append-only; #26–#30 area).
- [ ] Tests (Python parts fully offline; LLM behavior is interactive UAT):
  - `test_reference_loader.py` — `topics.yaml` parses; `seeds` flat/deduped; `topic_keys` correct
  - `test_cli.py` (extended) — `fetch-candidates` writes correct `candidates.json` (respx-mocked Congress, keyword-filtered by `topics.yaml` seeds); `render-classified` renders only the provided in-scope bills, rejects/flags `topics ⊄ topic_keys`, updates the index; `backfill --no-llm` unchanged
  - `test_agents.py` — each `.claude/agents/*.md` and `.claude/commands/zwiad-backfill.md` parse (valid frontmatter, expected model/tools, agent names consistent with the command)

## Acceptance Criteria
- [ ] `fetch-candidates` writes `candidates.json` containing enriched `Bill`s, keyword-filtered by the `topics.yaml` seed lexicon (offline, respx).
- [ ] `render-classified` renders only the in-scope bills it is given, validates `topics ⊆ topic_keys`, and updates the index; re-running identical input is byte-identical (clean `git status`).
- [ ] `backfill --no-llm` still renders every keyword-passing bill with the deterministic CRS summary, no subagents.
- [ ] Only `topics[]` is persisted to frontmatter; confidence/rationale/criterion are session-transient, never committed.
- [ ] Interactive UAT (open session, regular plan usage — no API key, no `claude -p`): `/zwiad-backfill congress=118 limit=5` filters off-topic bills via the classifier and renders in-scope federal pages with Claude summaries, amendment explanations, and `topics[]`.
- [ ] Rubric UAT (decision 17): appropriations rider / ceremonial resolution / seed-term-only-in-whereas bills → classified out; a genuine AI-transparency bill → classified in (eyeballed against the subagent's stated criterion).
- [ ] pytest + ruff + pyright (strict) all green on the Python parts.

## Decisions Made This Phase
(seeded from the brainstorming session + the Zwiad-precedent investigation + the June-15 Agent-SDK-credit article)
- **LLM runs via an interactive Claude Code session dispatching `.claude/agents/*.md` subagents (Task tool), on the user's regular plan usage.** Supersedes PLAN.md decision 12 and the earlier `claude -p`/Agent-SDK/API options. *Why:* per support.claude.com (eff. 2026-06-15), `claude -p` and the Agent SDK draw a separate, capped monthly Agent SDK credit (then bill API rates); only interactive Claude Code uses regular plan limits. The user is fine keeping a terminal open. *Trade-offs:* not headless/cron-able; classification logic lives in subagent prompts (validated by interactive UAT, not deterministic offline unit tests); the Python deterministic steps stay fully testable. *Revisit if:* automation/throughput needs outgrow an open session → reconsider `claude -p`-on-credit or API.
- **Architectural pivot: Claude Code orchestrates (slash command); Python = deterministic tooling + gitignored JSON staging handoffs** (`data/runs/<id>/`), mirroring Zwiad. Ripples into PHASE-06 (`run.py` → command) and PHASE-10 (cron → in-session scheduling), to be addressed in those phases.
- **Subagents in `.claude/agents/`; classifier reads `topics.yaml`** (single source preserved, no rubric duplication); summarizer/amendment-explainer are tool-less with bill data passed inline.
- **Phase 04 ships all three agents** (classify + summarize + amendments), per PLAN.md.
- **Classifier runs after `fetch`, before summarize/amendments**, reading title + the cheap CRS-extract summary (the only summary available pre-LLM for Congress candidates).
- **Classifier output is transient except `topics[]`** (applied to the bill before render); `in_scope` gates rendering; confidence/rationale/criterion are session-logged, not committed — re-renders stay byte-identical.
- **Amendment explanations are batched one subagent call per bill.**
- **`topics.yaml` is the single source** for both the recall keyword seeds (Python) and the classifier rubric (subagent).
