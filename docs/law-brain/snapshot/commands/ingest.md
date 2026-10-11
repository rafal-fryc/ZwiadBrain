<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\.claude\commands\ingest.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

---
description: Ingest a legal source (statute, case, guidance, article, URL) into the law brain.
argument-hint: <path-or-url>
---

You are performing an **ingest** operation in the law brain. Read `CLAUDE.md` first if you have not already this session. Pay particular attention to the confidentiality rules.

Source to ingest: `$ARGUMENTS`

## Procedure

1. **Classify the source before anything else.**
   - Statute / regulation? Case? Regulator guidance? Enforcement decision? Framework document? Commentary / article? Client-specific material?
   - If client-specific: **stop** and ask the user (a) whether to store, (b) what to de-identify, (c) whether anything is privileged. Only proceed with explicit direction.
2. **Acquire the source.**
   - If URL: WebFetch, save a clean markdown snapshot to `sources/<YYYY-MM-DD>-<kebab-slug>.md` with a header block noting the original URL, fetch date, and publisher/authority.
   - If local path: copy to `sources/` preserving filename or renaming to kebab-slug. PDFs stay as-is; wiki notes reference them.
3. **Read the source fully.** For long statutes, read the provisions the ingest is about in full — skimming is not acceptable for legal text.
4. **Identify touchpoints.** Grep `index.md` and wiki filenames. Check especially for:
   - An existing canonical page for this statute/regulation (update don't duplicate).
   - Related cases, guidance, or concepts that should gain a cross-reference.
5. **Plan the updates.** Tell the user your plan before writing (especially for regulations — one canonical page, amendments appended; new cases get their own page).
6. **Write wiki updates** per schema in `CLAUDE.md`:
   - Cite the specific articles/sections in the body, not just in Citations.
   - Populate `jurisdiction` accurately.
   - Add bidirectional `[[slug]]` cross-references.
   - Update `updated:` date.
7. **Update `index.md`.** Add entries with jurisdiction tag in brackets, e.g. `[[regulation-eu-ai-act]] — horizontal AI rulebook, risk-tiered (EU, 2024)`.
8. **Append one line to `log.md`:**
   ```
   <today> <time> | ingest | <primary-slug> | <short note: what was ingested and what legal question it informs>
   ```
9. **Report to the user:** pages created/updated, cross-references added, any interpretive tensions or open questions you surfaced, and whether the source contradicts existing wiki claims.

## Rules

- Never edit `sources/` contents after copying.
- If a source contradicts an existing wiki page, flag it — cite both sides, let the user decide which is authoritative.
- Distinguish the rule (statutory text) from commentary in the wiki page — keep them visually separate.
- If a source is primarily a tech/how-to-build piece, stop and suggest the `tech/` brain instead.
