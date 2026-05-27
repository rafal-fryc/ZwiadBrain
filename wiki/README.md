# ZwiadBrain Wiki

This directory is **the committed product** of ZwiadBrain: standardized Markdown pages
(with YAML frontmatter) tracking U.S. federal and state **legislation** and **enforcement
actions** in **AI, privacy, and cybersecurity**.

Everything else — raw scrapes in `data/raw/`, the SQLite index/watchlist — is *derived* and
gitignored. It is rebuilt from these pages via `zwiadbrain reindex`, so a fresh clone is
fully self-contained. **The frontmatter of these pages is the source of truth.**

## Organization

```
wiki/
  federal/
    bills/         # Congress.gov bills (legislative history assembled on enactment)
    enforcement/   # FTC + federal enforcement actions
  states/
    {ca,ny,tx,co,va,wa,il}/
      bills/        # LegiScan-tracked state bills
      enforcement/  # state Attorney General enforcement actions
  review-queue.md  # pending law-brain link proposals awaiting human accept/reject
  links.yaml       # permanent record of law-brain link decisions
```

## Page types

- **Bill page** — what the bill does (plain-language summary), status & timeline, amendments
  (each with a plain-language "what changed"), the standardized legislative history assembled
  once enacted, full-text version links, related bills, and a `## Commentary & Analysis`
  section carrying commentary copied verbatim from the read-only law brain.
- **Enforcement page** — agency, respondent, allegations, outcome, significance, and the same
  `## Commentary & Analysis` section.

Bill evolution (amendments, status flips) is captured as git diffs over time — the git
history of this directory *is* the change record.
