<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\.claude\commands\brief.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

---
description: Assemble a legal memo / briefing on a topic from the law wiki.
argument-hint: <topic>
---

You are generating a **brief** in the law brain. Read `CLAUDE.md` first if you have not this session.

Topic: `$ARGUMENTS`

## Procedure

1. **Scope the brief.** Ask once — what form does the user want?
   - **IRAC memo** (issue / rule / analysis / conclusion) — default for a legal question.
   - **Client advisory** — plain-language explanation, less formal.
   - **Comparative chart** — e.g., GDPR vs CCPA on a specific point.
   - **Compliance checklist** — operational output.
   Also ask jurisdictional scope if not obvious from the topic.
2. **Pull relevant pages.** Read `index.md`, filter by jurisdiction, locate all touching wiki pages, read fully. Consult `sources/` for exact statutory text if needed.
3. **Compose the brief** using the form below (IRAC default; adapt if user chose another form).

```markdown
---
title: Brief — <topic>
type: brief
jurisdiction: [...]
tags: [brief, <topic-tags>]
created: <today>
updated: <today>
sources: [wiki/<page1>.md, wiki/<page2>.md, ...]
status: active
---

## Issue
The precise question being addressed, with jurisdictional scope.

## Rule
Statutory rules + controlling case law + regulator guidance, with inline citations.

## Analysis
Apply the rule. Engage counter-arguments. Flag splits and unsettled questions.

## Conclusion
Direct answer, with caveats. If the answer is "it depends," say what it depends on.

## Risks & open questions
- Risk 1
- Open question 1

## Authorities
- Primary: <statutes / cases / regulations>
- Secondary: <guidance / commentary>
- Wiki pages: [[slug-1]], [[slug-2]], ...
```

4. **Write the file** to `wiki/brief-<YYYY-MM-DD>-<kebab-topic>.md`.
5. **Add to `index.md`** under **Briefs** with jurisdiction tag.
6. **Append `log.md`:**
   ```
   <today> <time> | brief | <topic-slug> | <form> <jurisdictions>
   ```
7. **Report to user:** path to the brief, short summary of the conclusion, and wiki gaps you hit (candidates for `/ingest`).

## Rules

- Brief is work product for the user (the lawyer), **not** client-facing advice unless the user explicitly asks for that form.
- Distinguish settled rules from open questions. If the topic is genuinely unsettled, say so rather than forcing a conclusion.
- Cite primary authority for every rule statement. "The statute requires X" needs an article/section.
