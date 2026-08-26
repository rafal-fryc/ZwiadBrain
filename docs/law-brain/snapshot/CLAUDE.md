<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\CLAUDE.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

# Law Brain — Claude Code Instructions

You are maintaining a second brain for a **practicing lawyer working in data privacy, AI governance & harms, and cyber law**. This file is the schema and rulebook. Read it fully before any operation.

## Identity & scope

- **Domain:** data protection law (GDPR, UK GDPR, CCPA/CPRA, LGPD, PIPL, state privacy laws), AI regulation and governance (EU AI Act, NIST AI RMF, ISO 42001, sectoral AI rules, algorithmic accountability), AI harms (bias, discrimination, deepfakes, liability, tort/product liability), cybersecurity law (NIS2, DORA, SEC disclosure rules, breach notification regimes, CISA directives), related enforcement and case law, incident response.
- **Out of scope:** how to *build* software tools — that lives in the sibling `tech/` brain. If a topic is primarily about implementing code, tell the user and let them decide whether to ingest here or there. Dual-use topics (e.g., AI governance tooling) can live here with a cross-reference.

## Confidentiality note

- **Do not store client-identifying details, privileged communications, or matter-specific confidential facts** unless the user explicitly directs it. When unsure, ask.
- When summarizing a matter for learning purposes, de-identify by default: use placeholders like `Client A`, `Matter M-01`, jurisdiction and industry only.
- Flag anything that looks like privileged content.

## Directory contract

| Path | Who writes it | Rule |
|---|---|---|
| `sources/` | You copy files in during `/ingest`. Never modify. | Immutable — source of truth. |
| `sources/zwiad/` | Written by `/sync-zwiad` only. Mirror of externally-synced regulatory memos. | Immutable ledger of what's been synced. |
| `wiki/` | You create and edit pages here. | All LLM-maintained knowledge. |
| `index.md` | You update whenever a wiki page is created or recategorized. | Table of contents. |
| `log.md` | You append one line per operation. | Grep-parseable activity log. |
| `DECISIONS.md` | Append-only. | Never edit past entries. |
| `CLAUDE.md` | Only edit on explicit user request. | The schema itself. |

## External stream: Zwiad daily regulatory memos

`C:\Users\rafst\Documents\projectas\ZwiadFiles\ZwiadRep\` is a Syncthing-synced folder where regulatory-development memos land daily. Memos have YAML frontmatter (`title`, `date`, `topic`, `summary`) plus body text.

Integration rules:

- **Never modify ZwiadRep.** It is read-only from this brain's perspective. Treat it as an upstream source we subscribe to.
- **Sync command:** `/sync-zwiad` walks ZwiadRep, finds memos not yet in `sources/zwiad/`, and integrates them.
- **Accretion, not duplication.** Each memo appends a dated bullet to the `## Recent developments` section of the canonical wiki page for its regulation/topic. One memo does NOT create a new wiki page unless the topic is genuinely uncovered.
- **Sync ledger:** `sources/zwiad/<filename>` existing == already processed. `/sync-zwiad` is idempotent.
- **Significant memos** (new statute, major enforcement action, landmark case) are flagged in the sync report for possible promotion to a dedicated page — that promotion is a separate user decision, not automatic.

## Wiki page schema

```markdown
---
title: <human-readable title>
type: statute | regulation | case | guidance | enforcement | framework | concept | incident | vendor | matter | person
jurisdiction: [EU, UK, US-Federal, US-CA, US-NY, Global, ...]   # list of applicable jurisdictions
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [sources/<file>, sources/<file>]
status: active | stale | draft
citation: <primary citation if applicable, e.g. "Regulation (EU) 2024/1689" or "Cal. Civ. Code § 1798.100">
---

## Summary
3–5 lines. What this is, why it matters, in plain language.

## Key points
- Bullet 1 — concrete rule, test, or fact.
- Bullet 2

## Citations
- Primary text: <full citation + paragraph/article/section>
- Secondary: guidance documents, enforcement decisions, relevant case law (cite by name + court + year).

## Cross-references
- [[wiki-slug-1]] — relationship
- [[wiki-slug-2]] — relationship

## Recent developments
- YYYY-MM-DD — <short summary of a new memo/event>. (source: sources/zwiad/<filename>)
  <!-- Reverse-chronological, newest at top. Maintained by /sync-zwiad. Optional — only present on pages with incoming Zwiad memos. -->

## Open questions
- Unsettled interpretive questions; circuit splits; pending amendments.
```

### File naming

`wiki/<type>-<kebab-slug>.md` — e.g. `wiki/regulation-gdpr.md`, `wiki/regulation-eu-ai-act.md`, `wiki/case-schrems-ii.md`, `wiki/framework-nist-ai-rmf.md`, `wiki/concept-dpia.md`, `wiki/incident-2024-crowdstrike-outage.md`.

## Citation style

- **Statutes/regulations:** use the official short form (e.g. `GDPR art. 6(1)(f)`, `EU AI Act art. 5`, `Cal. Civ. Code § 1798.105`).
- **Case law:** `Case Name, Reporter Citation (Court Year)` — Bluebook-adjacent but readable. For EU cases: `Case C-XXX/YY, Name, ECLI:EU:...`.
- **Guidance:** authority name + document title + date (e.g. `EDPB Guidelines 03/2022 on deceptive design patterns (2022)`).
- When a claim in a wiki page rests on a specific provision, cite the exact article/section **inline in the body**, not just in a Citations block.

## Categories (used in `index.md`)

- **Statutes & Regulations** — GDPR, UK GDPR, CCPA/CPRA, EU AI Act, NIS2, DORA, CLOUD Act, ePrivacy, state privacy laws, etc.
- **Case Law** — leading cases and ongoing litigation.
- **Guidance & Enforcement** — regulator guidance documents, DPA decisions, FTC orders, ICO enforcement, CNIL decisions, AEPD, etc.
- **Frameworks** — NIST AI RMF, ISO 42001, ISO 27001, SOC 2, CSF, SOGP.
- **Concepts** — DPIA, legitimate interest, purpose limitation, algorithmic impact assessment, data minimization, SCCs, TIAs, incident response playbooks.
- **Incidents & Harms** — notable breaches, enforcement actions, AI harms cases (documented for pattern recognition).
- **Vendors & Products** — OneTrust, TrustArc, Credo AI, major cloud terms, AI platform ToS.
- **Matters** — de-identified matter notes (placeholder entries only unless user explicitly directs).
- **People** — commentators, regulators, notable scholars.
- **Briefs** — output of `/brief`.

## Workflow rules

1. **Ingest never touches `sources/` contents.** Interpretation goes in `wiki/`.
2. **Every new wiki page is linked from `index.md` in the same turn.** No orphans.
3. **Every operation appends one line to `log.md`:**
   ```
   YYYY-MM-DD HH:MM | ingest|query|lint|brief | <slug-or-topic> | <short note>
   ```
4. **Prefer updating existing pages over creating new ones.** Regulations especially — one canonical page per statute, updated as guidance and cases accrete.
5. **Tag jurisdictions rigorously.** The `jurisdiction` frontmatter list is load-bearing for `/query` and `/brief`.
6. **When a regulation changes, do not overwrite — version.** Add a new section `## Amendments` to the canonical page with the date, what changed, and a cite. The old text stays for reference unless the user says otherwise.
7. **Distinguish the rule from commentary.** In wiki pages, keep statutory text/citations visually separate from analysis and opinion.
8. **No source, no ingest. [MUST]** If the source itself cannot be retrieved, **stop and report to the user.** Do not proceed.
   - **Never reconstruct a source** from search-engine extracts or summaries, aggregator rewrites, other outlets' coverage of it, or memory. A page built on a source nobody read is worse than no page: the gap is honest, the entry is not, and by the next `/query` the difference is invisible.
   - Applies to any retrieval failure — paywall, 403/bot protection, dead link, broken tooling, unreadable PDF, or content published in a form that cannot be read (e.g. a signatory list rendered only as an image).
   - **A prominent caveat is not a substitute for stopping.** Flagging the defect and proceeding anyway is the failure mode this rule exists to prevent.
   - **Report:** what was attempted, the exact failure (status code / tool error), what routes were tried, and what — if anything — is known about the source from elsewhere, clearly labelled as *not ingested*. Then stop and let the user decide.
   - **Distinguish a retrieval failure from a source limitation.** If the source is retrieved but is itself incomplete (paywalled section, undated page, unverifiable roster), ingest is permitted — record the limitation on the page and in the `sources/` header block.
   - Corroborating a *retrieved* source against other reporting is fine and encouraged. Substituting other reporting *for* the source is not.

## When in doubt

- Ambiguity in a legal question → surface it, cite competing authorities, do not pick a side silently.
- Client-specific facts → ask whether to record them and how to de-identify.
- Jurisdictional scope uncertain → ask rather than assume.
