# The law brain

ZwiadBrain has a dependency that lives outside this repository. `/zwiad-sync-lawbrain` reads a
separate knowledge base — the **law brain** — and copies its analysis verbatim onto tracked bill
and enforcement pages. This folder documents what that thing is.

It is worth documenting here for three reasons:

1. **The dependency is real but invisible.** It is configured by a single absolute path
   (`LAW_BRAIN_PATH` in `.env`), so nothing in the committed tree reveals what sits on the other
   end.
2. **The law brain is not a git repo.** Its design — schema, rules, five command workflows —
   exists in exactly one place on one machine, with no version history.
3. **The two systems are easy to confuse**, and the naming makes it worse. See
   [`architecture.md`](architecture.md).

## Contents

| Path | What it is |
|---|---|
| [`architecture.md`](architecture.md) | The law brain's schema, invariants, five command pipelines, and its relationship to ZwiadBrain |
| `snapshot/` | Verbatim copies of the law brain's operational files — **not authoritative** |

## About the snapshot

`snapshot/` holds the law brain's own `CLAUDE.md` (its schema and rulebook), its `DECISIONS.md`,
and the five slash commands that constitute its entire implementation. Each file carries a
header stamping its source path and copy date.

**The law brain is authoritative.** These copies exist so this repo records the design of what
it depends on, and so that design has *some* version history. They will drift. Nothing in
ZwiadBrain reads them — they are documentation, not configuration.

Deliberately **not** copied: any `wiki/` page content, `sources/`, `index.md`, or `log.md`. The
law brain holds a practicing lawyer's work product under a confidentiality-by-default rule, so
only the operational scaffolding is mirrored here. The snapshotted files were screened before
copying: they mention confidentiality only as rules, never as client facts.

## Refreshing it

Re-copy the seven files, preserving each stamp header and updating its date:

```bash
LB="$LAW_BRAIN_PATH"
cp "$LB/CLAUDE.md" "$LB/DECISIONS.md" docs/law-brain/snapshot/
cp "$LB"/.claude/commands/*.md docs/law-brain/snapshot/commands/
# then re-add the stamp header to each file and update architecture.md if the schema changed
```

Worth doing when the law brain's schema, workflow rules, or command set change — not on every
page edit, which is constant.
