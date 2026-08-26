# Citation-only tracker rows — disposition (2026-07-24)

The Orrick tracker cites 96 laws by statute section rather than bill number, 94 unique.
They cannot be joined to `wiki/states` by the `tracker-gap` cross-check, which keys on
`(state, chamber class, digits)`. This is the triage.

`resolves-to-bill` rows were parsed out of the tracker's own `law_link` and then VERIFIED
against LegiScan's enacted masterlists — the URL parse alone is a guess. North Dakota
proved why: its document URLs carry the LC **draft** number, which parsed into bills that
are unrelated (HB 1064 is about postsecondary institutions) or do not exist (SB 529, SB 34,
SB 908). The ND rule was removed; those six rows are `unparsed` and need real lookup.

| state | law (tracker's name) | citation | disposition | detail |
|-------|----------------------|----------|-------------|--------|
| az | Amendment of Arizona Intimate Images Law | Arizona Revised Statutes Section 13-1425 | resolves-to-bill | SB 1462 — LegiScan: enacted |
| ca | Real Estate Digitally Altered Images Disclosures | Cal. Bus. & Prof. Code § 10140.8 | resolves-to-bill | AB 723 — LegiScan: enacted |
| ky | AI Electioneering Communications | KRS 117.001 | resolves-to-bill | SB 4 — LegiScan: enacted |
| ky | Government Use of AI Law | KRS 42.720 - 42.742 | resolves-to-bill | SB 4 — LegiScan: enacted |
| md | AI Utilization Review | Md. Code Ann., Ins. §§ 15-10A-06, 15-10B-05. | resolves-to-bill | HB 820 — LegiScan: enacted |
| me | Communications with Consumers via AI | 10 MRSA c. 239 | resolves-to-bill | HP 1154 — LegiScan: NOT FOUND |
| mt | Montana Explicit Synthetic Media Law | MCA Title 45, Chapter 5, Part 6 | resolves-to-bill | SB 413 — LegiScan: enacted |
| mt | Privacy in Communications Law | MCA Section 45-8-213 | resolves-to-bill | HB 514 — LegiScan: enacted |
| mt | Property Right in Use of Names, Voices, and Visual Likenesse | MCA Title 30, Chapter 14, Section 1 | resolves-to-bill | HB 513 — LegiScan: enacted |
| nm | New Mexico Campaign Reporting Act Amendment | N.M. Stat. Ann. § 1-19-26 et seq. | resolves-to-bill | H 182 — LegiScan: enacted |
| nv | AI for Mental and Behavioral Health Care | Nev. Rev. Stat. Chapter 629 | resolves-to-bill | AB 406 — LegiScan: ambiguous |
| nv | AI for School Counseling | Chapter 391 of NRS | resolves-to-bill | AB 406 — LegiScan: ambiguous |
| nv | General AI Chatbots and Mental Health Services | Nev. Rev. Stat. Chapter 433 | resolves-to-bill | AB 406 — LegiScan: ambiguous |
| ok | Amendment of Oklahoma Law Governing Distribution of Intimate | Section 1040.13b | resolves-to-bill | HB 1364 — LegiScan: enacted |
| ri | Deceptive and Fraudulent Synthetic Media in Election Communi | General Laws, Title 17-30-1 to 4 | resolves-to-bill | S 816 — LegiScan: ambiguous |
| tx | Act Relating to the Regulation and Use of AI by Governmental | Chapter 2054, Government Code, Subchapter S | resolves-to-bill | SB 1964 — LegiScan: enacted |
| ar | Ownership of Model Training and Generated Content | Arkansas Code Title 18-4-101 | unparsed |  |
| ca | California AI Transparency Act As Amended by AB 853 (2025) | Cal. Bus. & Prof. Code § 22757 et seq. | unparsed |  |
| co | Colorado AI Act As amended by SB26-189 | Co. Rev. Stat. § 6-1-1701 et seq. | unparsed |  |
| co | Colorado Candidate Election Deepfake Disclosures Law | Co. Rev. Stat. 1-45-111.5 to 111.7 and 1-46- | unparsed |  |
| co | Colorado Privacy Act | Col. Rev. Stat. § 6-1-1301 et seq. Reprinted | unparsed |  |
| co | Colorado Protecting Consumers from Unfair Discrimination in  | Co. Rev. Stat. 10-3-1104.9 Reprinted from We | unparsed |  |
| ga | Prohibition on Nude or Sexually Explicit Electronic Transmis | Ga. Code § 16-11-90 | unparsed |  |
| la | Louisiana AI Intimate Image Law | 14 La. Rev. Stat. Ann. § 73.14 | unparsed |  |
| la | Louisiana Deepfake Law | 14 La. Rev. Stat. Ann. § 73.13 | unparsed |  |
| mn | Minnesota Consumer Data Privacy Act | Minn. Stat. § 325O et seq. | unparsed |  |
| nd | AI CSAM Amendments | North Dakota Century Code Section 12.1-27.2- | unparsed |  |
| nd | AI Political Advertising Disclaimer Law | ND Century Code, Chapter 16.1-10 | unparsed |  |
| nd | An Act Relating to Sexually Expressive Images | N.D. Cent. Code § 12.1-27.1-01 | unparsed |  |
| nd | North Dakota Harassment Law | North Dakota Century Code Section 12.1-17-07 | unparsed |  |
| nd | North Dakota Stalking Law | North Dakota Century Code Section 12.1-17-07 | unparsed |  |
| nd | North Dakota Unmanned Aerial Vehicle and Robot Law | North Dakota Century Code 29-29.4-01 to 06 | unparsed |  |
| nh | Responsive Generative Communication Law | New Hampshire Chapter 270:1 | unparsed |  |
| nj | New Jersey Data Privacy Act | N.J. Rev. Stat. § 56:8-166.4 et. seq. | unparsed |  |
| nv | Nevada AI Political Advertising Law | NRS Chapter 294A.347-95 | unparsed |  |
| ut | Utah Artificial Intelligence Policy Act | Utah Code § 13-72-301 et seq. | unparsed |  |
| va | Artificial Intelligence-Based Tools | Code of Virginia, Section 19.2-11.14 | unparsed |  |
| wi | Advertising Enhanced by Technology Law | Wis. Stat. § 452.136(1m) | unparsed |  |
| ca | Amendment of California CSAM Laws | Cal. Penal Code Part 1; Title 9; Chapter 7.5 | statute-text |  |
| ca | California Bot Act | Cal. Bus. & Prof. Code § 17940 –17943 | statute-text |  |
| ca | California Government AI Inventory Law | Cal. Gov. Code § 11546.45.5 | statute-text |  |
| ct | Connecticut Data Privacy Act | Conn. Gen. Stat. § 42-515 et seq. | statute-text |  |
| ct | Transportation Network Company Dynamic Pricing | Conn. Gen. Stat. § 13b-118 | statute-text |  |
| de | Delaware Personal Data Privacy Act | Del. Code tit. 6, § 12D-101 et seq. | statute-text |  |
| ia | Harassment | Iowa Code § 708.7 | statute-text |  |
| ia | Sexual Exploitation of a Minor | Iowa Code § 728.12 | statute-text |  |
| id | Idaho Explicit Synthetic Media law | Idaho Code § 18-6606 | statute-text |  |
| id | Relating to Personhood | I.C. § 5-346 | statute-text |  |
| il | Artificial Intelligence Video Interview Act | 820 ILCS 42 | statute-text |  |
| in | Indiana Consumer Data Protection Act | Ind. Code. §24-15-1 | statute-text |  |
| ky | Kentucky Consumer Data Protection Act | Ky. Rev. Stat. § 367.3611 et seq. | statute-text |  |
| md | Amendment to the Maryland CSAM Statute | MD. Code., Crim. Law 11-208 | statute-text |  |
| mo | Pornography and Related Offenses | R.S.Mo § 573.010 | statute-text |  |
| mt | Montana Consumer Data Privacy Act | Montana Code Ann. § 30-14-2801 et seq. | statute-text |  |
| nh | New Hampshire Privacy Act | N.H. Rev. Stat. § 507-H:8 | statute-text |  |
| nj | New Jersey Bot Act | NJ Rev. Stat. § 56:18-1 et seq. | statute-text |  |
| ny | Artificial Intelligence Companion Models | New York General Business Law Article 47 | statute-text |  |
| ny | Artificial Intelligence Deceptive Practices Act | N.Y. Election Law § 14-106 | statute-text |  |
| ny | Artificial Intelligence Deceptive Practices Act | N.Y. Civ. Rights Law § 50 et seq. | statute-text |  |
| ny | Contracts for the Creation and Use of Digital Replicas | General Obligations CHAPTER 24-A, ARTICLE 5, | statute-text |  |
| ny | New York Algorithmic Pricing Disclosure Act | New York General Business Law Article 22-A,§ | statute-text |  |
| ny | New York Landlord Algorithmic Pricing Law | New York General Business Law Article 22,§ 3 | statute-text |  |
| sc | Real Estate AI Responsibility Law | S.C. Code Ann. § 40-57-820 | statute-text |  |
| tn | Tennessee Information Protection Act | Tenn. Code. Ann. § 47-18-3301 | statute-text |  |
| tx | Texas Data Privacy and Security Act | Tex. Bus & Com. Code § 541.051(b)(5)(C) | statute-text |  |
| va | Hospital / Nursing Home Virtual Assistant Law | Va. Code Ann. § 32.1-127 | statute-text |  |
| va | Virginia Consumer Data Protection Act | Va. Code Ann. § 59.1-577A(A)(5) | statute-text |  |
| wi | 2023 Wisconsin Act 123 | Wis. Stat. § 11.1303 | statute-text |  |
| wy | Amendment to Intimate Image Law | Wy. Code § 6-4-306 | statute-text |  |
| wy | Sexual Exploitation of Children | Wy. Code § 6-4-303 | statute-text |  |
| ca | Artificial Intelligence in Health Care Services | Cal. Gov. Code § Section 1339.75 AB 3030 | already-tracked | ca-2023-ab-3030 |
| ca | California Companion Chatbot | Cal. Bus. & Prof. Code § 22601 et. seq. | already-tracked | ca-2025-sb-243 |
| ca | Civil Actions | Cal. Civ. Code § 1714.46 | already-tracked | ca-2025-ab-316 |
| ca | Data Broker Registration AI Disclosures | Cal. Civ. Code § 1798.99.82 | already-tracked | ca-2025-sb-361 |
| ca | Health Advice From Artificial Intelligence | Cal. Bus. & Prof. Code § 4999.9 | already-tracked | ca-2025-ab-489 |
| md | Maryland Online Data Privacy Act | Md. Code Ann. § 14-4601 et seq. | already-tracked | md-2024-hb-567 |
| ny | The Responsible AI Safety and Education (RAISE) Act Passed b | New York General Business Law, Article 44-B | already-tracked | ny-2025-s-8828 |
| tn | Ensuring Likeness, Voice, and Image Security (ELVIS) Act of  | Tennessee Code Annotated, Section 47-25-1101 | already-tracked | tn-2023-hb-2091 |
| ut | AI Applications Related to Mental Health | Utah Code § 13-72a-101 | already-tracked | ut-2025-hb-452 |
| ut | Artificial Intelligence Consumer Protection Amendments | Utah Code § 13-75-102 | already-tracked | ut-2025-sb-226 |
| ut | Artificial Intelligence Consumer Protection Amendments | Utah Code § 13-75-101 to 106 | already-tracked | ut-2025-sb-226 |
| wy | Protecting Kids from Deepfakes and Exploitative Images | Wy. Code §§ 6-4-303; 6-4-308 | already-tracked | wy-2026-hb-102 |
| wy | Self-Harm Systems | Wy. Code § 6-4-701 | already-tracked | wy-2026-hb-102 |
| wy | Wyoming AI Criminal Liability | Wy. Code § 6-1-206 | already-tracked | wy-2026-hb-102 |
| wy | Wyoming AI Developer Civil Liability | Wy. Code § 1-1-143 | already-tracked | wy-2026-hb-102 |
| wy | Wyoming Nonconsensual Synthetic Sexual Material | Wy. Code § 6-4-307 | already-tracked | wy-2026-hb-102 |
| ca | Law Enforcement Usage of Artificial Intelligence | Cal. Civ. Code § 13663 | already-rejected | ca-2025-sb-524 |
| ri | Rhode Island Data Transparency and Privacy Protection Act | R.I. Gen. Law § 6-48.1-1 et seq. | already-rejected | ri-2024-s-2500 |
| ut | Law Enforcement Usage of Artificial Intelligence | Utah Code § 53-25-601 to 602 | already-rejected | ut-2025-sb-180 |
| ut | Unauthorized Artificial Intelligence Impersonation Amendment | Utah Code § 45-3-2 et. seq. | already-rejected | ut-2026-sb-256 |
| ca | California Consumer Privacy Act Regulations | 11 CCR § 7001 et seq. | non-bill |  |
| ca | Employment Regulations Regarding Automated-Decision Systems, | Civil Rights Council Employment Regulations  | non-bill |  |
| nj | Rules Pertaining to Disparate Impact Discrimination (N.J.A.C | N.J.A.C. 13:16 | non-bill |  |
| ny | NYC AI Employment Law | (Local Law 144) | non-bill |  |

## Counts

| disposition | n | meaning |
|---|---:|---|
| resolves-to-bill | 16 | a bill number recovered from the tracker's link; 12 verified enacted, 3 ambiguous (NV AB 406 x3, RI S 816 — need a session pin), 1 not found (ME HP 1154, a paper number needing its LD) |
| already-tracked | 16 | the codified form of a law already on the wiki |
| already-rejected | 4 | already decided out of scope under its bill number |
| statute-text | 32 | link points at codified statute; no bill recoverable from the URL |
| unparsed | 22 | link carries no usable bill number (incl. the 6 ND draft-number rows) |
| non-bill | 4 | administrative regulations or a NYC local law — outside the LegiScan state-bill pipeline by construction |

## Confirmed genuine gaps found while triaging

- **Montana Consumer Data Privacy Act** (Mont. Code Ann. 30-14-2801) — Montana has exactly
  one tracked page (`mt-2025-sb-212`); the MTCDPA is not among them.
- **California Bot Act** (Cal. Bus. & Prof. Code 17940-17943) — SB 1001 of 2018, which
  predates the 2019 floor of the state backfill, so no sweep has ever seen it.

Most of the remaining `statute-text` and `unparsed` rows name acts already tracked under
their bill number (CT SB 6, DE HB 154, IL HB 2557, IN SB 5, KY HB 15, NH SB 255, TN HB 1181,
TX HB 4, VA HB 2307, CO SB 190, CO SB 205, CA SB 942/AB 853, MN HF 4757, NJ S 332,
UT SB 149), so the true remaining gap here is far smaller than 94.


## Outcome (2026-07-25) — resolved and pulled

The `resolves-to-bill` rows plus a full lookup pass over the `statute-text` and `unparsed`
buckets produced **34 candidate bills**, resolved by searching LegiScan's FULL TEXT for the
statute section each row cites and confirming the hit against the enacted masterlists.

Two candidates were dropped because LegiScan shows them at status 2 (Engrossed), not
enacted: CA AB 410 (Bots: disclosure) and CA AB 1609 (Customer service chatbots). The
year-mismatch guard also refused a 2023 CA AB 410 about shared mobility devices — a
different law that happens to share the number.

**32 bills classified: 10 in scope, 22 rejected.** New states: **AR, NV** (36 tracked).

Tracked from this pass:

| bill | law |
|---|---|
| ar-2025-hb-1876 | Ownership of generative-AI output and trained models (Act 927) |
| ca-2017-sb-1001 | **California B.O.T. Act** — bot-disclosure law, below the 2019 backfill floor |
| ct-2023-sb-3 | CTDPA amendment — consumer health data, health-facility geofencing ban, minors |
| ky-2025-sb-4 | State AI governance + synthetic media in electioneering, with medium liability |
| ky-2025-hb-473 | KY CDPA amendment — HIPAA exemption, profiling disparate-impact assessments |
| md-2025-hb-820 | AI in health-insurance utilization review |
| mt-2023-sb-384 | **Montana Consumer Data Privacy Act** — the confirmed coverage gap |
| mt-2025-hb-513 | Name/voice/visual-likeness property right incl. digital visual depictions |
| nv-2025-ab-406 | AI marketing/programming limits + AI in mental & behavioural health care |
| tx-2025-sb-1343 | Data broker registration and website notice requirements |

**KY SB 4 is the one that tests the D91 line.** Its AI-governance half binds only state
agencies, and its synthetic-media half is an election provision — both normally out. It is
tracked because subsection (5) makes the *disseminating medium* or its advertising sales
representative liable for stripping a required disclosure, which is a platform duty of the
same kind that keeps CA AB 2655 tracked while CA AB 2355 is not.

**Six D91 overrides** applied on the same basis as the bill-numbered half: AZ SB 1462,
ID H 575, MT SB 413, MT HB 514 and ND HB 1386 (person-facing synthetic-imagery offences),
and ND HB 1167 / RI S 816 (election-actor disclosure).

**Provenance note:** the session's 200-subagent cap was reached partway through, so 12 of
the 32 verdicts were classified in-session against `reference/topics.yaml` rather than by
the `classifier` subagent. Those carry a `[classified in-session]` marker in the verdict
record (`tracker-citation-verdicts-2026-07.json`).

**Text-extraction note:** five sidecars came back as a status marker only (AR HB 1876,
CT SB 3, MT SB 384, MT HB 513) or as leginfo navigation chrome (CA SB 1001). All five were
re-fetched from the LegiScan text document and read directly; each sidecar header records
how. MT HB 513's latest LegiScan document is the AMENDED version, not an enrolled copy.

### Still open

- **SC H 4754** — a real-estate licensing omnibus; Orrick cites S.C. Code 40-57-820 as an
  AI-responsibility provision that may ride inside it. Rejected pending enacted text.
- **NM HB 182** — "Election Changes", title-only; election-actor and out under D91 anyway.
- The remaining `statute-text` rows whose named acts are already tracked under their bill
  number needed no action; a handful of ND rows (16.1-10 political advertising beyond
  HB 1167, 29-29.4 robot provisions) resolved to bills that were then rejected on scope.
