# Accuracy Fixes — TODO

Source: full accuracy audit of all 113 bill pages, 2026-07-01 (details in `accuracy-review-2026-07-01.md`).
Each item lists the page, the exact location, and the correct value. Check off as fixed.
Reminder: `leg_history.narrative` (frontmatter) and the body "Legislative Journey" section are duplicates — fix BOTH everywhere a narrative is edited.

---

## Priority 1 — Wrong-law / wrong-scope errors (substantive)

### tx-2023-sb-2013.md
- [x] Narrative describes the 2021 LSIPA (SB 2116) prohibition framework as SB 2013's content. Rewrite the "As enacted" portion: SB 2013 actually adds an "affiliate" definition, grants ERCOT criminal-history access + background checks for grid-security-critical positions, requires Ch. 113 compliance attestations from ERCOT-registered entities, requires reporting/attestation of critical grid-equipment purchases from designated-country companies (5-year lookback), authorizes registration suspension and AG audits.
- [x] Narrative: don't call SB 2013 itself "the Lone Star Infrastructure Protection Act" (that is SB 2116's name); say it amends the LSIPA.
- [x] Narrative: "Rep. Phil King also credited as a House author" → King was a **Senator** (SD-10) in 2023, a Senate joint author. Hunter is the House sponsor.

### il-2023-hb-4875.md
- [x] Narrative: remove the claim that the bill "voids contracts that substitute a digital replica … unless represented by counsel or a union" — that provision is HB 4762 (Digital Voice and Likeness Protection Act), not HB 4875.
- [x] Narrative: SFA3 did NOT add "an extended 50-year post-mortem protection period" — the 50-year term has existed since PA 90-747 (1999); the amendment only inserted "or digital replica" into it.
- [x] Narrative: "Reps. Mary Edly-Allen" — she is a **Senator**, joined as Chief Senate Sponsor 2024-04-19, never a House cosponsor.

### ca-2023-sb-1223.md
- [x] Narrative: "first dedicated neural-data privacy statute enacted anywhere in the United States" → Colorado HB 24-1058 (signed 2024-04-17) was first; reframe as first in California / second US state.
- [x] Statement quote typo: "neurtechnology" → "neurotechnology" (wiki-introduced typo inside a verbatim quote; fix in `statements[0]` frontmatter and body).

### ca-2019-ab-1355.md
- [x] Narrative: the "reasonably" insertion into the "capable of being associated with" standard belongs to AB 874 (Ch. 748), carried via AB 1355's SEC. 7.5 double-jointing. Attribute to AB 874.

### il-2019-hb-2557.md (AI Video Interview Act)
- [x] Summary describes the INTRODUCED bill. Rewrite from the chaptered text: no "in writing" notice requirement, no "written consent", AI analyzes "the applicant's video interview" (not "facial expressions"); include Sections 10/15 sharing/deletion as enacted.

### va-2023-hb-2024.md
- [x] Summary materially mischaracterizes the enacted law. Correct: (1) only "the Commonwealth" (state agencies/political subdivisions) — not any person/website — is barred from publication after written demand; (2) no immediate-family coverage; (3) penalty is CRIMINAL (Class 6 felony, 6-month mandatory minimum for publication with intent to coerce/intimidate/harass), not civil; (4) also adds judges/magistrates to voter-registration address-confidentiality eligibility.

### va-2024-hb-707.md
- [x] Summary: "known minors" → "known children (under 13)" with parental-consent (COPPA) requirements (VCDPA "Child" definition).

### va-2022-hb-714.md
- [x] Summary last sentence: bill did NOT codify the AG cure process (pre-existed in 2021 VCDPA §59.1-584(B)). Correct description: expands nonprofit exemption (political orgs, certain 501(c)(4)s), repeals §59.1-585 (Consumer Privacy Fund), redirects penalty proceeds to the revolving trust fund.

### wa-2019-hb-1071.md
- [x] Summary: AG notification threshold is "more than 500" Washington residents (501+), not "500 or more."

### wa-2023-hb-1155.md (My Health My Data)
- [x] Narrative: Senate amendments did NOT extend response timelines to 45 days (already in House-passed bill; Senate only clarified authentication doesn't extend it). Senate amendments added phased compliance dates (2024-03-31 / 2024-06-30 small businesses) and the JLARC review.

### ca-2025-sb-833.md
- [x] Summary overstates scope: applies only to STATE-AGENCY operators of critical infrastructure (§8954.50(g)); §8954.51(a)(2)(B) allows periodic after-the-fact review where pre-approval is "substantially disruptive." Rewrite.

### ca-2025-ab-1064.md
- [x] Summary: enrolled (vetoed) text imposes duties on "operators" only, not "both developers and operators"; the "directed at or likely to be used by children" framing reflects an earlier version — enacted framing prohibits an operator from making a companion chatbot available to a child (knowledge standard phases in 2027-01-01).

### ca-2025-ab-1337.md
- [x] Summary mischaracterizes: core change is removing the Information Practices Act exemption for LOCAL agencies (effective 2028-01-01) + revising the "personal information" definition; not just "state agencies" data-handling updates.
- [ ] Page stale/self-contradictory: timeline and version list end 2026-05-06 / 2025-05-23 but the attached .text.md is the 2026-06-01 Amended-Senate version. Add the June 2026 actions (amended 6/1; hearings set/canceled through 6/25) — or re-run refresh for this bill.

### il-2023-hb-2954.md (Doxing Act)
- [x] QUOTE MISATTRIBUTION: "Today marks a critical step forward…" is attributed to Julie Morrison (`verified: true`) but the source press release attributes it to **David Goldenberg, ADL Midwest Regional Director**. Reattribute (role: other) or replace with Morrison's actual quote ("As technology evolves, so must our laws." / "The measure signed into law today is a positive step…").
- [x] Summary is the synopsis of House Floor Amendment No. 1, not the Act. Rewrite to describe the Act (doxing definition, civil action, injunctive relief).

### co-2024-sb-205.md (CO AI Act)
- [x] Stale effective-date claim: "February 1, 2026 effective date" — delayed to 2026-06-30 by SB25B-004 (special session, signed 2025-08-28), then repealed/replaced by SB26-189 (signed 2026-05-14, effective 2027-01-01); SB24-205 never took effect as written. Add this to the page.
- [x] Quote fidelity: Polis signing letter — "tamper innovation" → "hamper innovation" (per source).

### 119-hr-9076.md
- [x] Summary claims "no bill text is available in the public record" — contradicted by the page's own Full Text link and .text.md. Rewrite: the bill requires a court order for use of a USPS mail cover. Sponsor Scanlon, introduced 2026-05-29, House Judiciary.

---

## Priority 2 — Wrong dates, votes, and attributions in narratives

### California
- [x] **ca-2019-ab-1130**: narrative "exposed passport numbers for approximately 327 million hotel guests" → "exposed personal information of ~327 million guests, including passport numbers for a subset" (passport numbers ~25.55M).
- [x] **ca-2019-ab-1130**: related_media video "Senate Floor Session, September 11, 2019 (final Senate passage 26-12)" → Senate passed 2019-09-05; 9/11 was enrollment. Fix date/title/note.
- [x] **ca-2019-ab-1146**: narrative "clarifying amendment in July 2019" → June 2019 (amendments 6/14 and 6/28; later floor amendment 9/6).
- [x] **ca-2019-ab-1281**: narrative "approved by the Senate Appropriations Committee on consent (9-0)" → 9-0 was Senate JUDICIARY (2020-08-13); Appropriations was bypassed via Senate Rule 28.8.
- [x] **ca-2021-ab-825**: narrative "Senate passed the bill on reconsideration 37–0" → passed 30–0 (37-0 was the reconsideration-granted motion).
- [x] **ca-2023-ab-1824**: narrative "introduced on January 16, 2024" → January 11, 2024.
- [x] **ca-2023-ab-1836**: narrative concurrence "57-8 on September 1, 2024" → August 31, 2024.
- [x] **ca-2023-ab-1836**: Jodi Long statement + The Wrap media item dated 2024-08-31 as "Senate passage" coverage → article is 2024-07-03, covers Senate Judiciary passage (July 2). Fix date + context in both.
- [x] **ca-2023-ab-3030**: narrative committee dates: Health 16-0 "April 10" → April 9; P&CP 10-0 "April 24" → April 23 (report dates vs vote dates).
- [x] **ca-2023-ab-3030**: narrative "Senate floor amendments" → Senate COMMITTEE amendments (Health 6/26-27, Approps 8/15).
- [x] **ca-2023-ab-3030**: remove bogus hearing entry "AB 3030 (Calderon) – APCP Analysis" (2024-04-21) — it's an analysis document, not a hearing; dedupe the double-listed Health hearings.
- [x] **ca-2023-ab-801**: narrative Senate Judiciary "(also 7–0)" → 11-0.
- [x] **ca-2023-sb-362**: narrative APCP "voted 7-0 on June 26, 2023" → June 27, 2023.
- [x] **ca-2023-sb-362**: narrative "deferred the portal's launch to August 1, 2026" → portal established by Jan 1, 2026; Aug 1, 2026 is when brokers must begin accessing it. Distinguish the two deadlines.
- [x] **ca-2023-sb-793**: narrative "Judiciary Committee approved it on April 21, 2023" → April 25 (4/21 = analysis date).
- [x] **ca-2023-sb-793**: narrative "Appropriations (August 14, 2023)" → August 16 (8/14 = analysis date).
- [x] **ca-2023-sb-793**: fix impossible sequencing ("After Senate amendments on April 10 and April 17 … heard … on April 12") — the 4/17 amendment came after the 4/12 hearing.
- [x] **ca-2019-ab-1564**: related_media Jones Day entry: title → "The CCPA Amendments that Survived the California Legislature", date → mid/late Sept 2019 (not 2019-09-01).
- [x] **ca-2019-ab-1564**: related_media EFF article date 2019-04-01 → 2019-04-23.
- [x] **ca-2025-ab-979**: Irwin "related" statement + CalMatters media item date 2025-10-01 → 2025-10-09.

### Texas
- [x] **tx-2021-sb-15**: narrative "House Transportation Committee, chaired by Rep. Phil King" → chair was Terry Canales; King was House sponsor and conference chair.
- [x] **tx-2021-sb-15**: narrative agencies "chiefly TxDOT and Parks & Wildlife" → Texas Department of MOTOR VEHICLES (and TPWD).
- [x] **tx-2021-sb-2116**: narrative "filed … on April 1, 2021" → filed March 12, 2021 (4/1 = first reading/referral).
- [x] **tx-2021-sb-2116**: narrative "six Senate cosponsors" but lists seven names → "seven".
- [x] **tx-2023-hb-4**: narrative "received by the Senate on May 1, 2023" → April 5, 2023 (5/1 = first reading/referral).
- [x] **tx-2023-sb-768**: narrative "reported favorably … on May 5, 2023" → April 26, 2023 (5/5 = report filed with Coordinator).
- [x] **tx-2023-sb-2105**: narrative "committee report was distributed May 22" → May 20 (5/22 = sent to Local & Consent Calendar).

### New York
- [x] **ny-2019-a-5635** (SHIELD): narrative Senate vote "42–21" → 42–20.
- [x] **ny-2019-a-5635**: related_media "Consumer Protection Meeting" note "5-2 favorable vote" → 5 aye + 2 aye-with-reservations, 0 nay (reported 7-0).
- [x] **ny-2023-s-2659**: narrative "no recorded opposition at any stage" → contradicted by 60-1 (2023 Senate) and 140-5 (2024 Assembly); only the 2024 Senate and committee votes were unanimous.
- [x] **ny-2023-s-7676**: narrative initial referral "Judiciary Committee" → Rules Committee (2023-10-02); Judiciary on 2024-01-03.
- [x] **ny-2023-s-7694**: narrative + YouTube related_media note say S7695B is also Chapter 120 → S7695B is Chapter **121**; only S7694A is Chapter 120.

### Colorado
- [x] **co-2022-sb-171**: narrative + related_media title "46-3-16" House vote → 46 Yes, 16 No, 3 Excused (46-16-3).
- [x] **co-2026-hb-1139**: narrative Senate 3rd reading "32-0" → 32-3 (No: Baisley, Rich, Zamora Wilson).

### Federal
- [x] **118-hr-2670** (FY24 NDAA): Votes section — Senate conference-report vote (Record Vote 343) dated 2023-12-14 → 2023-12-13; de-duplicate rows (House roll 723 ×2, Senate 343 ×2).
- [x] **118-hr-2670**: narrative sequencing — Senate cleared the conference report Dec 13, BEFORE the House's Dec 14 vote.
- [x] **118-hr-2670**: narrative "first [formal conference] in two years" → three years (last: FY2021 NDAA, Dec 2020).

### Virginia
- [x] **va-2021-hb-2307** (VCDPA): Marsden natlawreview statement date 2021-03-02 → on/before 2021-02-17 (article date).
- [x] **va-2021-hb-2307**: Blue Virginia related_media date 2021-03-02 → 2021-03-06 (publication date).
- [x] **va-2021-hb-2307**: reword narrative to disambiguate — after HB 2307's House passage it narrates SB 1392's path; "Senate concurred in the House substitute 32-7 on Feb 19" is SB 1392, not HB 2307 (whose sequence was reversed: House concurred 85-8).

---

## Priority 3 — Duplicate / phantom / corrupted vote and statement rows

- [x] **ca-2019-ab-1146**: remove corrupted Votes row `2019-09-11 S: Assembly 3rd Reading AB1146lass="statusCell"> — Passed 8-0` (HTML fragment; 8-0 is the 7/9 committee vote; real 9/11 floor vote 40-0 is on the line above).
- [x] **ca-2021-ab-2273**: remove phantom duplicate Senate floor vote dated 2022-08-29 (only real vote 2022-08-30, 33-0).
- [x] **ca-2025-sb-53**: remove spurious duplicate Senate concurrence "2025-09-12 S … Passed 29-8" (real vote 2025-09-13).
- [x] **ca-2025-sb-53**: dedupe the Newsom signing quote (appears as "Gavin Newsom"/press AND "Gov. Gavin Newsom"/signing — same quote/date/URL).
- [x] **il-2023-sb-2979**: remove duplicated Cunningham 2024-05-16 statement (identical quote/speaker/date/URL ×2); dedupe the duplicate Senate Judiciary hearing entries; fix committee-vote date 2024-03-12 → 2024-03-13 (narrative + hearing entries).
- [x] **co-2019-hb-1197**: Votes row "Adopt amendment L.006 — Failed 0-0" → L.006 was ADOPTED without objection.
- [x] **co-2022-hb-1041**: remove contradictory "Passed 23-9" row (official: 24-9-2; keep 24-9).
- [x] **tx-2021-sb-15**: dedupe 2021-04-14 Senate votes (4 rows for 2 votes).
- [x] **tx-2025-hb-149**: dedupe repeated 5/23 Senate vote rows; dedupe hearings (5 entries for 3 events); replace History.aspx-as-hearing-source entries.
- [x] **tx-2023-sb-2105**: dedupe hearings (5 entries for 3 events); replace History.aspx-as-hearing-source entry.
- [x] **ca-2019-ab-1355**: dedupe the two duplicate 4/23/2019 APCP hearing entries.
- [ ] **ca-2023-ab-2013 / ab-1824 / ab-1836 / ab-2602 / ab-801**: fix off-by-one Senate-floor Ayes in Status & Timeline (38→39, 39→40, 32→33, 36→37, 38→39 respectively — leginfo roll calls are authority; narratives/Votes already correct). Consider a pipeline fix: refresh LegiScan snapshots for these.

---

## Priority 4 — Systematic passes (scriptable)

- [x] **ILGA link migration (all IL pages)**: retired URL families 404 everywhere — `BillStatus.asp?…`, `/legislation/<GA>/HB|SB/*.htm`, `/legislation/votehistory/*`, `/legislation/publicacts/<GA>/*.htm`. Working replacements already used elsewhere on the pages: `/ftp/legislation/<GA>/BillStatus/HTML/…`, `/documents/legislation/…`, `/Legislation/publicacts/view/…`. Migrate `sources.State source`, Sources, Enactment, Votes, Versions, Full Text sections.
- [x] **chamber: House → Assembly** for CA hearings (ca-2019-ab-1146, ab-1564 ×2, ab-947, ca-2021-ab-335 ×2, ca-2023-ab-2655/ab-3030/ab-3286 …) — grep `chamber: House` under states/ca.
- [x] **source_type: CREC on state sources** — relabel to a state committee-analysis/press type (ca-2019-ab-1130 ×2, ca-2021-ab-2273 ×3, ca-2023-sb-942, ny-2021-a-3904 ×2).
  - [ ] FOLLOW-UP (found during the 2026-07-02 sweep, not in the original audit): `source_type: CREC` also remains on state pages **ca-2023-ab-2013, ca-2023-ab-3030, ca-2025-sb-53, ny-2023-s-7676, ny-2023-s-7694, ny-2023-s-7695, tx-2023-hb-4, tx-2023-sb-2105**. Each needs the correct per-source label (analysis/hearing/press/news/other) — left for a follow-up pass since the right label is source-dependent.
- [x] **"Conference Sub" → "Governor's substitute"** where no conference occurred: va-2023-hb-2024 (HB2024H2), va-2024-hb-707 (HB707H2).
- [x] **Dead link**: co-2024-hb-1104 Senate 3rd-reading roll-call URL (`leg.colorado.gov/content/hb24-1104vote55d98d`) → 404; find current bill_votes-style URL. Check other `leg.colorado.gov/content/…vote…` links for the same pattern.
- [ ] **CO 2026 pages** (hb-1139, hb-1210, sb-189): replace epoch placeholder dates "1969-12-31" on Versions/Full Text; hb-1210 has a "Chaptered" version label on a vetoed bill.
- [ ] **Stale refreshes**: re-run refresh for ca-2025-sb-354 (missing June 2026 actions: Asm Insurance 11-3 on 6/17/26, now in Asm P&CP) and ca-2025-ab-1337 (June 2026 amendments/hearings); reconcile stale `update_date < latest_action_date` (ca-2025-sb-354, ca-2025-ab-1337, va-2026-sb-85, wa-2025-hb-1671).
- [x] **119-s-146** (TAKE IT DOWN): reclassify 118th-Congress predecessor items (2024 hearings, Cruz 2024-07-31 committee-vote statement, Klobuchar 2024-11-19, Cruz/Berry/Mani/Toups 2024-06-26) from `relation: on_bill` → `related`, matching the convention used on 116-hr-7898.

---

## Suspected issues to adjudicate before fixing (not confirmed)

- ca-2023-ab-947: Senate floor 38-0 (journal) vs 39-0 (roll call w/ add-on) — page states both without noting the discrepancy.
- ca-2025-sb-53: 2025-07-16 APCP vote 9-0 (timeline) vs 10-0 (Votes) — leginfo itself disagrees; prefer roll call or annotate. Also upstream law-brain page `regulation-california-sb53-tfaia`: "SB 535's 10^26 threshold" likely typo for SB 53.
- ca-2023-ab-1824: "after Senate Appropriations cleared it" — was a Rule 28.8 bypass.
- ca-2023-ab-3286: "Senate Appropriations hearing 6/24/2024" listed but bill bypassed via Rule 28.8.
- ca-2023-sb-362 / sb-793: "principal coauthor" labels vs leginfo's regular-coauthor listings.
- il-2023-hb-2130: narrative "without a single dissenting vote" vs 9-4-0 House committee vote; Votes labels 5/11 Senate action "Motion" (was Third Reading).
- il-2019-hb-2557 / il-2023-hb-2954: narratives imply cosponsors present at introduction; all were added later.
- il-2023-hb-3773: "Chaptered" version dated 2024-08-14 vs PA date 2024-08-09.
- il-2023-sb-2979: WGEM source links SB 1506, not SB 2979 (weak source); "Enrolled Bill Text" media URL is the introduced-version filename.
- co-2024-hb-1130: narrative conflates concurrence (60-2) with repass (62-0).
- co-2024-sb-205: H.001 failure attributed to 3rd reading May 8; failed 21-43 on May 7 (2nd reading).
- ny-2019-a-5635: timeline chamber tags scrambled on mixed A5635/S5575 rows (LegiScan artifact).
- ny-2023-s-7694: "four members recording reservations" detail unverified.
- va-2024-hb-707: Amendments entry "Senate amendments not adopted — [adopted]" self-contradictory.
- va-2026-hb-1257: duplicated timeline row (2026-02-02 ×2).
- va-2026-hb-1261: "companion to H.B. 1257" — same-chamber near-duplicate, not a companion as term of art.
- wa-2025-hb-2157: status "Introduced" vs Rules X-file timeline; 20 identical unlabeled amendment entries.
- wa-2023-hb-1155: narrative attributes Senate changes to the L&J committee amendment; enacted changes rode the floor striking amendment.
- tx-2019-sb-936 / tx-2021-hb-3746: trivial enrolled-version date discrepancies between Versions and Related Media.
- il-2025-hb-4980: Summary "meaningful human control" vs statutory "meaningful and continuing human review".
- Docling extraction gaps: il-2025-hb-3720 / hb-4980 .text.md missing bill page 1.
