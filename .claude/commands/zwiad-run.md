---
description: Run the whole ZwiadBrain pipeline in one interactive session — refresh + discover + enforcement + law-brain — auto-committing per source and writing a scan-log entry. Built to be triggered by an external interactive-session runner (D26).
argument-hint: "[--dry-run]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain full run

Orchestrate every enabled source flow in ONE interactive session. This command does not
re-implement the sources — it sequences the existing commands, auto-commits each source's
changes, and records a grep-parseable run-log. Designed so an external runner that opens an
interactive Claude Code session can trigger ZwiadBrain on a schedule (D26: LLM work stays
interactive; no `claude -p`).

**Arguments:** `--dry-run` lists the intended steps and per-source commit messages without
running subagents or writing/committing anything.

## Principles
- **Per-source isolation (D54):** if a step fails, record the error, commit whatever already
  succeeded, and continue to the next source. Never abort the whole run on one failure.
- **Auto-commit per source (PHASE-10):** after a source produces changes, commit the touched
  paths (`wiki/**`, plus `wiki/links.yaml` / `wiki/review-queue.md` for the law-brain step)
  with a conventional message. No changes → no commit.
- **Law brain is read-only (D2).** Never write under `LAW_BRAIN_PATH`.
- Pick a `RUN_ID`: the short basename of the newest `data/runs/<id>/` directory created this
  pass (timestamp form), used in the run-log header.

## Steps

Run each in order. For each, follow that command's own procedure (read its
`.claude/commands/<name>.md`). Track a per-source result `{source, summary, commit|null}` for
the run-log.

1. **Refresh tracked items** — follow `/zwiad-refresh`. Record `refresh-federal` and
   `refresh-state` results. Commit changed pages: `chore(scan): refresh tracked bills (<n> changed)`.
2. **Discover new federal** — follow `/zwiad-backfill` (since-window). Commit:
   `chore(scan): discover federal bills (<n> new)`.
3. **Discover new state** — follow `/zwiad-scan-states`. Commit:
   `chore(scan): discover state bills (<n> new)`.
4. **Enforcement** — follow `/zwiad-scan-enforcement` (FTC + enabled AGs). Commit:
   `chore(scan): enforcement actions (<n> new/updated)`.
5. **Law-brain sync** — follow `/zwiad-sync-lawbrain`. Commit `wiki/**` + `wiki/links.yaml`
   + `wiki/review-queue.md`: `chore(scan): law-brain commentary (<n> linked, <m> review)`.
6. **Reindex + log:**
   - `uv run zwiadbrain reindex` (rebuilds the gitignored index — nothing to commit).
   - Identify newly-enacted bills with no `leg_history` (flag only — do NOT run
     `/zwiad-leg-history`; list them in the summary).
   - `Write` the assembled run-summary JSON to `data/runs/<RUN_ID>/run-summary.json`
     (fields: `run_id`, `sources[]` with `{source, summary, commit|null}`,
     `leg_history_flagged[]`, `errors[]`).
   - `uv run zwiadbrain run-log --in data/runs/<RUN_ID>/run-summary.json`
   - `git add scan-log.md && git commit -m "chore(scan): log run <RUN_ID>"`

## Report
Print the consolidated summary: per-source counts + commit shas, any errors, and the
leg-history TODO list. For `--dry-run`, print the intended steps and commit messages only.
