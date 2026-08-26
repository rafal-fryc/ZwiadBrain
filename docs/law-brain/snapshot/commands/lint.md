<!--
  SNAPSHOT — do not edit here.
  Source: <law-brain>\.claude\commands\lint.md
  Copied: 2026-08-26
  The law brain is authoritative. This copy exists because the law brain is not a
  git repo; it will drift. Refresh per docs/law-brain/README.md.
-->

---
description: Health-check the law wiki for contradictions, stale pages, orphans, broken links, citation gaps, and schema violations.
---

You are performing a **lint** pass on the law wiki. Read `CLAUDE.md` first if you have not this session.

This is **read-only.** Produce a report. The user decides what to fix.

## Checks

1. **Schema violations** — any `wiki/*.md` missing required frontmatter (`title`, `type`, `jurisdiction`, `created`, `updated`, `status`) or using an unknown `type`.
2. **Jurisdiction tag missing or implausible** — pages where `jurisdiction` is empty or suspiciously narrow/wide for the topic.
3. **Orphan pages** — files in `wiki/` not mentioned in `index.md` under any category.
4. **Broken cross-references** — `[[slug]]` links pointing to a non-existent file.
5. **Stale pages** — `status: stale` OR `updated` > 90 days ago on `status: active` pages. **Flag these seriously for law** — regulations and guidance move.
6. **Missing sources** — `sources:` frontmatter references a file not present in `sources/`.
7. **Citation gaps** — wiki pages with zero citations (every legal page should cite something); citations without a recognizable pattern (`art.`, `§`, `v.`, `ECLI:`, Reporter).
8. **Contradictions** — pages whose rule statements conflict across the same jurisdiction. Flag with quoted text from both pages.
9. **Index hygiene** — entries in `index.md` pointing to non-existent wiki pages; duplicates.
10. **Confidentiality red flags** — scan for what looks like client identifiers (proper-noun company names with matter-like contexts), privileged-communication markers ("privileged", "A/C", "work product"), or specific facts that should be de-identified. Report for user review — **do not auto-redact.**

## Report format

```
# Law Wiki Lint Report — <today>

## Schema violations (N)
## Jurisdiction issues (N)
## Orphan pages (N)
## Broken links (N)
## Stale pages (N)  ← prioritized: regulations and enforcement move fast
## Missing sources (N)
## Citation gaps (N)
## Contradictions (N)
## Index issues (N)
## Confidentiality flags (N)  ← user review only
```

Append one line to `log.md`:
```
<today> <time> | lint | full | <N issues across M categories>
```
