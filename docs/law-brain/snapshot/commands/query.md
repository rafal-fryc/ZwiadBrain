<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\.claude\commands\query.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

---
description: Answer a legal question from the wiki with proper citations; file durable synthesis back.
argument-hint: <question>
---

You are performing a **query** in the law brain. Read `CLAUDE.md` first if you have not this session.

Question: `$ARGUMENTS`

## Procedure

1. **Scope the question.** Identify jurisdictions in play. If ambiguous, ask (one short question — "EU, US, or global?"). Do not assume.
2. **Locate relevant pages.** Read `index.md`. Filter by jurisdiction tag and category. Grep `wiki/` for keywords as a second pass.
3. **Read the candidate pages in full.** Consult `sources/` only if the wiki lacks the specific provision text or holding needed.
4. **Synthesize the answer** with this discipline:
   - **Separate rule from application.** State the rule with citation first, then apply it to the facts.
   - **Cite primary authority inline.** Every rule statement points to a statute (`GDPR art. 6(1)(f)`), case, or regulation. Every wiki claim points to the wiki page path (`wiki/<file>.md`).
   - **Flag splits, ambiguity, unsettled questions.** Do not manufacture false clarity.
   - **Jurisdictional scope** — be explicit about which jurisdiction(s) your answer addresses.
5. **Assess durability.** If the synthesis produced new cross-references or a novel analytical frame worth keeping, propose a wiki update to the user and apply it on confirmation.
6. **Append one line to `log.md`:**
   ```
   <today> <time> | query | <topic-slug> | <short note: question and which authorities answered it>
   ```

## Output format

- **Question restated** (one line, with jurisdictional scope).
- **Short answer** (1–3 lines).
- **Analysis** — rules with citations, application, tensions.
- **Citations** — primary authorities + wiki pages consulted.
- **Gaps** — what the wiki doesn't cover (candidates for `/ingest`).
- **Caveats** — limits of a wiki-based answer; when to consult live research / Westlaw / Lexis / official gazette.

## Rules

- **This is not legal advice to third parties.** You are assisting the user (the lawyer) in their own work product. Never output in a form that reads like advice to a client without the user explicitly asking for that form.
- If no relevant pages exist, say so clearly. Offer to answer from general knowledge with a disclaimer, and suggest what to ingest.
- For any answer that could turn on a recent regulator position or recent case, flag recency — the wiki may be stale.
