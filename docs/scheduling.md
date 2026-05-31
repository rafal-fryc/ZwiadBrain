# Scheduling ZwiadBrain

ZwiadBrain has no built-in scheduler. All LLM work runs as interactive Claude Code subagents
on the regular plan (D26) — headless `claude -p` / the Agent SDK are forbidden — so a session
must be open and triggered.

## The entrypoint

`/zwiad-run` runs the whole pipeline (refresh → discover federal/state → enforcement →
law-brain → reindex) in one interactive session, auto-commits per source, and appends a block
to `scan-log.md`.

## Triggering it on a schedule

Point any runner that can **open an interactive Claude Code session** at `/zwiad-run` on your
desired cadence (a few times/week is the design target). ZwiadBrain is deliberately
**scheduler-agnostic** — it does not ship Task Scheduler / cron wiring. The runner is the only
thing that needs scheduling; ZwiadBrain just exposes the one command.

Why not a plain cron job running shell? Because the LLM dispatch (classifier / summarizer /
enforcement / law-brain subagents) must run in an interactive session to stay on the regular
plan (D26). A runner that drives an interactive session satisfies this; a headless shell does
not.

## Auditing runs

`scan-log.md` (committed) carries one grep-parseable block per run — per-source counts, the
commit shas, flagged-for-manual-leg-history bills, and any per-source errors.
