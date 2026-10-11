<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\DECISIONS.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

# Decisions — Law Brain

Append-only. Add a new entry rather than editing past ones.

---

## 2026-04-13 — Karpathy LLM-wiki pattern chosen
**Chosen:** Three-layer markdown wiki (sources / wiki / schema) maintained by Claude Code.
**Alternatives:** Obsidian-only (manual), Notion, dedicated legal knowledge tools (e.g. Harvey, Casetext).
**Why:** Plain markdown is tool-independent, diff-able, survives vendor changes, and the LLM carries the maintenance burden. Dedicated legal AI tools are expensive, opaque, and don't compound as personal knowledge.
**Trade-offs:** No Westlaw/Lexis integration; citation format is hand-maintained; no conflict-check integration. Acceptable for a personal knowledge layer — this is not a DMS.
**Revisit if:** Wiki exceeds ~500 pages or user wants citation validation tooling.

---

## 2026-04-13 — Confidentiality-by-default for matter content
**Chosen:** No client identifiers, no privileged content, no matter-specific confidential facts in the wiki unless user explicitly directs. De-identified placeholders (`Client A`, `Matter M-01`) are the default.
**Alternatives:** Store freely with encryption; store nothing about matters at all.
**Why:** A personal knowledge brain should not become a privilege hazard. De-identified pattern extraction gives 80% of the learning value with near-zero risk. Encryption-at-rest does not solve the problem that LLM operations on the content may leak into logs.
**Trade-offs:** Some matter-specific nuance is lost. Can be selectively overridden per-ingest by explicit user direction.
**Revisit if:** User moves to a fully local/offline LLM setup, or adopts a formal KM tool with privilege controls.

---

## 2026-04-13 — Semantic search deferred
**Chosen:** Rely on Claude's built-in Grep/Glob/Read over `wiki/` and `index.md`, plus jurisdiction-tag filtering.
**Alternatives:** qmd (BM25+vector), dedicated legal retrievers.
**Why:** Premature until the wiki has real mass. `index.md` + jurisdiction tags + filename conventions give deterministic retrieval for small-to-medium wikis.
**Trade-offs:** `/query` may miss pages without good cross-referencing. That will be the signal to add search.
**Revisit if:** `/query` misses relevant pages, or wiki exceeds ~150 files.

---

## 2026-04-13 — Isolated from tech brain
**Chosen:** `law/` is fully separate from `tech/` — own CLAUDE.md, own commands, own directory tree.
**Alternatives:** One shared brain with tags.
**Why:** Legal analysis benefits from focused context. Code snippets and framework docs in the same retrieval pool would add noise. User explicitly asked for separation.
**Trade-offs:** Dual-use topics (AI governance tooling, privacy-engineering products) may need manual cross-reference between brains.
**Revisit if:** A genuinely cross-cutting workflow emerges that justifies a shared layer.

---

## 2026-04-13 — Zwiad regulatory-memo stream integration
**Chosen:** Treat `C:\Users\rafst\Documents\projectas\ZwiadFiles\ZwiadRep\` as an external daily stream. Integrate via manual `/sync-zwiad` command that copies new memos to `sources/zwiad/` (the sync ledger) and accretes each as a dated bullet under `## Recent developments` on the relevant canonical wiki page.
**Alternatives:** (a) Auto-sync on session start via Claude Code hook; (b) scheduled daily agent via `/schedule`; (c) one wiki page per memo; (d) reference memos by absolute path without copying.
**Why:**
- **Manual trigger** keeps the human in the loop on confidentiality-sensitive content and avoids silent work at startup.
- **Accretion over per-memo pages** keeps canonical regulation pages evergreen and discoverable — `/query` and `/brief` don't have to chase a growing pile of `update-*.md` files.
- **Copy into `sources/zwiad/`** preserves the "sources/ is the single source of truth" schema and makes the sync idempotent (presence = processed).
- **ZwiadRep stays immutable from our side** so Syncthing's contract with the upstream editor is untouched.
**Trade-offs:**
- Requires user to remember to run `/sync-zwiad`. Staleness risk if ignored.
- Accretion buries individual memo identity — if a single memo later proves landmark, it needs manual promotion to a dedicated page.
- `/query` relies on the canonical page being the right routing target; if a memo is mis-routed on sync, it won't surface under the right topic.
**Revisit if:** Memo volume exceeds what manual sync can keep up with, or if a memo type emerges that doesn't fit any canonical page and the "create new canonical page" rule becomes noisy.

---

## 2026-08-10 — No source, no ingest: halt on retrieval failure
**Chosen:** User decision: if a source cannot be retrieved directly, `/ingest` **stops and reports**. Reconstructing a source from search-engine extracts, aggregator rewrites, other outlets' coverage, or memory is prohibited. Recorded as Workflow rule 8 in `CLAUDE.md`.
**Alternatives:** (a) Proceed with a prominently-caveated reconstruction (the prior de facto practice); (b) proceed only where two or more independent named outlets corroborate; (c) ingest a stub recording the failure, with no analysis.
**Why:**
- The precipitating case: CNBC 2026-07-17 (White House frontier-model access gating). WebFetch returned 403; the local headless-browser tool would not start. The article was reconstructed from search extracts plus one named-outlet summary and accreted onto `regulation-trump-eo-ai-innovation-security`, with caveats throughout.
- **Caveats decay; entries persist.** The reconstruction struck out a genuine open question on that page on the strength of a source that was never read. By the next `/query` or `/brief`, a caveated entry and a verified one are retrieved the same way and read the same way.
- The story in question was **anonymously sourced and denied on the record by the White House**. Where the legal interest lies precisely in the gap between what officials say and what they reportedly do, the exact wording is the whole content — and paraphrase destroys it.
- A brain used for legal work inherits the citation discipline of the practice. "I read a summary of it" is not a basis on which to record what a source says.
**Trade-offs:**
- Real coverage gaps where sources sit behind bot protection or paywalls. CNBC, Quartz, and similar will routinely fail.
- Fast-moving stories may go unrecorded at the moment they matter most.
- Shifts retrieval effort to the user (supplying text, a PDF, or an accessible mirror).
- Mitigation: the rule permits ingest where a source **is** retrieved but is itself incomplete — the limitation is recorded rather than the ingest refused.
**Revisit if:** A reliable authenticated retrieval path becomes available (working browser automation, a subscription-backed fetch tool), or the gap rate proves high enough that a "failure stub" tier — logging the attempt with no analysis — is worth adding as a middle option.
