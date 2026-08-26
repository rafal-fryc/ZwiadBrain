<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\.claude\commands\sync-zwiad.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

---
description: Sync newly-arrived regulatory memos from the ZwiadRep folder into the law brain, accreting each onto the canonical wiki page for its topic.
---

You are performing a **Zwiad sync** in the law brain. Read `CLAUDE.md` first if you have not this session.

## What Zwiad is

`C:\Users\rafst\Documents\projectas\ZwiadFiles\ZwiadRep\` is a Syncthing-synced folder where daily regulatory-development memos land. Memos have YAML frontmatter with at least `title`, `date`, `topic`, and `summary`, plus a body.

The law brain treats this as an **external daily stream**. Your job here is to integrate newly-arrived memos without duplicating wiki pages — each memo accretes onto the canonical page for its regulation/topic.

## Procedure

1. **Enumerate incoming memos.** List `*.md` files in `C:\Users\rafst\Documents\projectas\ZwiadFiles\ZwiadRep\`. Ignore `.stfolder` and any other Syncthing metadata.
2. **Filter to unsynced memos.** A memo is unsynced if no file with the same filename exists in `law/sources/zwiad/`. That directory is the sync ledger — if it's there, we've already processed it.
3. **Skip placeholder/seed memos.** If a memo's frontmatter or body clearly marks it as a placeholder, test, or seed (e.g. "seed memo", "placeholder", "safely delete", "hello-world"), skip it. List skipped memos in the final report but do not copy or process.
4. **For each real unsynced memo:**
   a. **Read the full memo.** Frontmatter + body.
   b. **Copy** (do not move) the memo to `law/sources/zwiad/<original-filename>`. The ZwiadRep folder is read-only from our side — never edit or delete anything there.
   c. **Route the memo to a canonical wiki page.** Use the frontmatter `topic`, the title, and the body to decide. Candidates:
      - An existing `wiki/regulation-*.md`, `wiki/framework-*.md`, `wiki/case-*.md`, `wiki/guidance-*.md`, or `wiki/concept-*.md` whose scope covers this memo.
      - If no candidate exists and the topic plainly warrants a canonical page (e.g. a new statute the wiki has never covered), create one per the `wiki/` schema in `CLAUDE.md` and add it to `index.md`.
      - If routing is ambiguous (multiple plausible canonical pages, or unclear whether to create a new one), **defer this memo** — list it in the report for user review, do NOT copy to `sources/zwiad/` yet, so it stays in the unsynced queue for the next run.
   d. **Append to the canonical page's `## Recent developments` section.** Create the section if it doesn't exist; put it after `## Key points` and before `## Cross-references`. Format each bullet:
      ```
      - YYYY-MM-DD — <one-line summary, usually from frontmatter `summary`, rewritten as needed for context>. (source: sources/zwiad/<filename>)
      ```
      Keep bullets in reverse-chronological order (newest at top of the section).
   e. **Update `updated:` frontmatter** on the canonical page to today's date.
   f. **If the memo crosses multiple canonical pages**, append a bullet to each, referencing the same source file.
   g. **If the memo is significant** (new statute, major enforcement action, landmark case, regulatory framework launch), flag it in the report — the user may want you to create a dedicated wiki page for it in a follow-up turn.
5. **Update `index.md`** if any new canonical page was created.
6. **Append one line per synced memo to `log.md`:**
   ```
   <today> <time> | sync-zwiad | <canonical-page-slug> | <memo filename>
   ```
7. **Report to the user.** Structure:
   - **Synced:** memos processed, with destination page(s) for each.
   - **Deferred:** memos needing human routing decision and why.
   - **Skipped:** placeholder/seed memos.
   - **Flagged as significant:** any memos the user may want promoted to dedicated pages.
   - **Errors:** anything unexpected (malformed frontmatter, unreadable files).

## Rules

- **ZwiadRep is read-only from our side.** Never write, edit, or delete anything there.
- **Idempotency:** re-running `/sync-zwiad` after a clean run should sync nothing. The ledger is `sources/zwiad/` — presence of the filename there means "done."
- **Never overwrite an existing `sources/zwiad/<filename>`.** If it's there, we already processed it; investigate rather than re-copy.
- **Confidentiality filter still applies.** If an incoming memo contains what looks like client-identifying detail or privileged content, flag it in the report and do NOT copy until the user decides.
- **Preserve the canonical-page principle.** Do not create `update-YYYY-MM-DD-*.md` pages from memos — accretion is the rule. Only create new canonical pages when the topic genuinely lacks one.
