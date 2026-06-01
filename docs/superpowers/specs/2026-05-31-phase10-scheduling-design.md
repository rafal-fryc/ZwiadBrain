# PHASE-10 — Scheduling: `/zwiad-run` orchestration + run-log

**Date:** 2026-05-31
**Status:** design approved (brainstorming); pending implementation plan

## Context & problem

ZwiadBrain's headline promise is a tracker that "stays current via a scheduled scan a
few times/week." The original plan used OS cron + headless `claude -p`. That was
abandoned:

- **D26** — all LLM work (classifier, summarizer, amendment-explainer, enforcement and
  law-brain subagents) runs as **interactive Claude Code subagents on the regular plan**.
  Headless `claude -p` / the Agent SDK draw a separate capped credit and do not support
  claude.ai subscription auth, so they are forbidden.
- **D27 / D41** — the pipeline is split at the LLM boundary: deterministic Python `fetch-*`
  detection verbs (zero LLM calls) + interactive slash commands that dispatch subagents.
  D41 explicitly deferred the scheduling decision to PHASE-10.

**New constraint from the user (this session):** scheduling will be driven *later* by an
external runner ("openclaw-like") that opens a **full interactive Claude Code session** and
runs one command. PHASE-10 must therefore expose a single, **scheduler-agnostic**
orchestration entrypoint that runs the whole pipeline in one interactive session and
**auto-commits per source**. PHASE-10 does **not** wire up any specific scheduler now.

## Goal

A single interactive orchestration command, **`/zwiad-run`**, that sequences every enabled
source flow (refresh → discover → enforcement → law-brain → reindex), **auto-commits each
source's changes** as it goes, appends a grep-parseable entry to a committed **`scan-log.md`**
via a small tested **`zwiadbrain run-log`** helper, and prints a consolidated summary. Plus a
brief, scheduler-agnostic **`docs/scheduling.md`**.

## Non-goals (YAGNI)

- No OS scheduler wiring (Windows Task Scheduler / cron) — the trigger is the external
  runner, built later by the user.
- No headless LLM (`claude -p` / Agent SDK) — violates D26.
- No `--sources` filter in v1 — run an individual existing command for a subset.
- No auto-run of legislative history — newly-enacted bills are **flagged** for a manual
  `/zwiad-leg-history <bill>` (it is the heaviest, rarest flow).
- No changes to the 6 existing commands — PHASE-10 is orchestration glue over proven units.

## Decisions captured this phase (to log as DECISIONS entries during implementation)

1. **Operating model:** a single interactive `/zwiad-run`, externally triggered,
   scheduler-agnostic. (Confirms D41's hybrid, collapsed to one interactive entrypoint
   because the runner can drive an interactive session that does both detection and dispatch.)
2. **Commit policy:** auto-commit per source; the git history is the audit trail. The law
   brain stays read-only throughout (D2).
3. **Build approach:** thin runbook composing the existing 6 commands + one tested Python
   `run-log` helper (mirrors the D27 "session assembles JSON → Python renders deterministically"
   seam).
4. **Leg-history:** flag newly-enacted bills lacking leg-history; do not auto-run.

## Components

### 1. `.claude/commands/zwiad-run.md` — orchestration runbook
An interactive session runs this one command. It sequences the source flows (below),
auto-commits per source, calls `run-log`, and prints a summary. The orchestration logic is
a runbook (prose) that invokes the existing commands' procedures — validated by interactive
dry-run like the other commands (D26), not by deterministic unit tests.

### 2. `zwiadbrain run-log` CLI verb + `scan-log.md`
- **Input:** a small run-summary JSON the session assembles (per-source outcome counts,
  commit shas or `none`, errors, run id, start/end timestamps).
- **Output:** appends one deterministic, grep-parseable block to repo-root **`scan-log.md`**
  (committed; append-only audit trail, mirrors the law brain's `log.md`).
- Pure/deterministic given its input + a timestamp (accepts `--at` for tests; defaults to
  now). Unit-tested.

### 3. `docs/scheduling.md`
Brief, scheduler-agnostic note: the entrypoint is `/zwiad-run`; it is designed to be
triggered by an external runner that opens an interactive Claude Code session; no coupling
to Task Scheduler/cron; D26 rationale (why not headless).

## Orchestration flow (the runbook)

Each step is independent — a step that fails logs its error, the run **commits whatever
succeeded before it**, and the run continues to the next source (per-source isolation, D54):

1. **Refresh tracked** federal + state — `/zwiad-refresh` (cursor-change detection;
   re-dispatch only changed; flip out-of-scope to `tracking:false`).
2. **Discover new** federal — `/zwiad-backfill` (since-window discovery).
3. **Discover new** state — `/zwiad-scan-states`.
4. **Enforcement** — `/zwiad-scan-enforcement` (discovery-driven; re-scan *is* the refresh,
   D52; covers FTC + the enabled state AGs).
5. **Law-brain sync** — `/zwiad-sync-lawbrain` (commentary attach; law brain read-only).
6. **`reindex`** (rebuilds the gitignored `data/cache` index — no commit), then assemble the
   run-summary JSON, call `run-log`, **commit `scan-log.md`** (`chore(scan): log run <id>`),
   and print the summary.

After each source that produced changes: **auto-commit** the touched paths (`wiki/**`, and
for the law-brain step `wiki/links.yaml` / `wiki/review-queue.md`) with a conventional
message, e.g. `chore(scan): refresh state bills (2 changed)`. No changes → no commit (clean
working tree). The **run id** is a short id the session derives from the per-run
`data/runs/<id>/` directory (its timestamp). Newly-enacted bills with no `leg_history` are
listed in the summary as a manual-leg-history TODO.

## `scan-log.md` entry format

Append-only block per run, grep-parseable:

```
## 2026-05-31T22:00Z  (run a1b2c3)
- refresh-federal : changed=1 → commit 9f3a21c
- refresh-state   : changed=0 → no-op
- discover-state  : new=2     → commit 4c7e88a
- enforcement     : new=1     → commit b2d5f10
- lawbrain        : linked=0 review=1 → commit 7e1aa90
- leg-history     : 1 enacted bill flagged (118-hr-2670) — run manually
- errors          : none
```

## Error handling / isolation

- Each source step is wrapped so a failure (API down, selector drift, subagent error) is
  recorded in the run-log `errors` line and does not abort the run.
- Partial commits are expected and fine (each source commits independently).
- Re-running `/zwiad-run` is safe: unchanged sources commit nothing; the underlying commands
  are idempotent (D20).

## Testing & acceptance

**Unit tests** (`run-log` helper):
- Given a run-summary JSON → exact expected appended block (fixed `--at`).
- Two runs append in chronological order; existing content preserved.
- Missing/extra/malformed fields handled gracefully (per-source line still emitted or a
  clear error line).

**Runbook** (validated by interactive dry-run, D26): a dry-run lists the intended per-source
steps and commit messages without applying.

**Acceptance criteria:**
- `/zwiad-run` runs the 6-step sequence end-to-end in one session.
- Each changed source is committed with a conventional message; unchanged sources commit
  nothing.
- A `scan-log.md` block is appended each run; the file is committed.
- A no-change run is a clean no-op except for the (always-appended) run-log block.
- The law brain is never written (D2).
- Newly-enacted bills lacking leg-history appear in the summary as a manual TODO.

## Open / deferred

- `--sources` filter on `/zwiad-run` (run an individual command meanwhile).
- Auto-running leg-history (currently flagged-only).
- Any openclaw/Task-Scheduler-specific wiring (the user builds the trigger later).
