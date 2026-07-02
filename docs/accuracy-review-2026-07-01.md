# Accuracy review findings (running log)

## Layer 1 — deterministic script (DONE)
0 structural errors across 257 pages. 22 warnings handed to agents for adjudication.

## IL 2025 SB batch (il-2025-sb-3220, il-2025-sb-3548) — CLEAN
Fully verified against ilga.gov. No errors, no dead links.

## CA batch B (ca-2019-ab-1130, ca-2019-ab-1146, ca-2019-ab-1281)

### ca-2019-ab-1130.md
1. CONFIRMED ERROR — narrative (frontmatter leg_history.narrative + body Legislative Journey): "exposed passport numbers for approximately 327 million hotel guests" overstates. 327M = guests with SOME exposed data; passport numbers only a subset (~25.55M). Fix: "exposed personal information of approximately 327 million guests, including passport numbers for a subset."
2. CONFIRMED ERROR — related_media video "Senate Floor Session, September 11, 2019 (AB 1130 final Senate passage 26-12)": Senate passed 2019-09-05 (26-12); 9/11 was enrollment/presentation. Date/title/note wrong.
3. MINOR — two Levine statements have source_type: CREC (federal) but source is CA Assembly committee analysis.

### ca-2019-ab-1146.md
4. CONFIRMED ERROR — Votes body section line ~341: corrupted row `2019-09-11 S: Assembly 3rd Reading AB1146lass="statusCell"> — Passed 8-0` — HTML scrape fragment; 8-0 is the 7/9/2019 Sen Judiciary committee vote, not a 9/11 floor vote (real floor vote 40-0 listed above). Remove row.
5. CONFIRMED ERROR — narrative says "clarifying amendment in July 2019"; Senate amendments were 2019-06-14 and 2019-06-28 (+ floor amendment 2019-09-06). Should say June 2019.
6. MINOR — hearings[0] has `chamber: House`; should be `Assembly`.

### ca-2019-ab-1281.md
7. CONFIRMED ERROR — narrative: "approved by the Senate Appropriations Committee on consent (9-0)" — 9-0 was Senate JUDICIARY 2020-08-13; Appropriations was bypassed via Senate Rule 28.8 to Consent Calendar 2020-08-19.

All 8 spot-checked quotes verified verbatim; chapters/signing dates/authors confirmed. No dead links.

## CA batch C (ca-2019-ab-1355, ca-2019-ab-1564)

### ca-2019-ab-1355.md
8. SUSPECTED/BORDERLINE — narrative credits AB 1355 with "inserting 'reasonably' into the 'capable of being associated with' standard" — that change belongs to AB 874 (Ch. 748), carried via AB 1355's SEC. 7.5 double-jointing contingency. Reframe: attribute to AB 874.
- MINOR — first two Hearings entries duplicate same 4/23/2019 APCP hearing.
- All votes/chapter (757)/dates verified correct. No statements on page.

### ca-2019-ab-1564.md
9. CONFIRMED ERROR — related_media Jones Day entry titled "CCPA Amendments Head to California Governor" (2019-09-01): real title is "The CCPA Amendments that Survived the California Legislature", date mid/late Sept 2019.
10. CONFIRMED ERROR — related_media EFF article dated 2019-04-01; actual pub date 2019-04-23.
11. MINOR — two hearings entries `chamber: House` (should be Assembly).
- All votes/chapter (759)/dates verified. No statements on page.

## CA batch D (ca-2021-ab-335, ca-2021-ab-825, ca-2021-ab-2273)

### ca-2021-ab-335.md — clean except:
12. MINOR — hearings `chamber: House` should be `Assembly` (x2).

### ca-2021-ab-825.md
13. CONFIRMED ERROR — narrative: "Senate passed the bill on reconsideration 37–0 on September 8, 2021" — 37-0 was the reconsideration-granted motion; actual passage was 30-0. Fix narrative to 30-0.
- Quotes verified; chapter 527, signing 2021-10-05 OK.

### ca-2021-ab-2273.md
14. CONFIRMED ERROR — Votes section: phantom duplicate Senate floor vote dated 2022-08-29 (Passed 33-0); only one real vote on 2022-08-30. Remove 08-29 row.
15. MINOR — three Wicks statements have source_type: CREC but source is CA Senate Judiciary committee analysis.
- Quotes verified; chapter 320, signing 2022-09-15 OK.

## CA batch 2 (ab-1824, ab-1836, ab-1971, ab-2602)

### ca-2023-ab-1824.md
16. CONFIRMED ERROR — narrative says introduced "January 16, 2024"; actual 2024-01-11 (Jan 16 is AB 1836's date, copy-over). Fix narrative (frontmatter + body).
17. CONFIRMED ERROR — timeline entry 2024-08-27 Senate vote "(Ayes 39. Noes 0.)"; leginfo says 40-0. Narrative/Votes correctly say 40-0.
- SUSPECTED — narrative "after Senate Appropriations cleared it"; actually Rule 28.8 bypass.

### ca-2023-ab-1836.md
18. CONFIRMED ERROR — timeline 2024-08-31 Senate vote "(Ayes 32. Noes 4.)"; actual 33-4.
19. CONFIRMED ERROR — narrative: concurrence 57-8 "on September 1, 2024"; actual August 31, 2024.
20. CONFIRMED ERROR — Jodi Long statement + The Wrap media dated 2024-08-31 as "Senate passage" coverage; article is 2024-07-03 covering Senate Judiciary (July 2) passage. Fix date + context.

### ca-2023-ab-1971.md — CLEAN (quotes verified).

### ca-2023-ab-2602.md
21. CONFIRMED ERROR — timeline 2024-08-27 Senate vote "(Ayes 36. Noes 1.)"; actual 37-1.
NOTE: systematic pattern — timeline Senate-floor Ayes off by one on AB 1824/1836/2602 (+ AB 2013 below): stale LegiScan snapshot vs leginfo authority.

## CA batch 3 (ab-2013, ab-2655, ab-3030, ab-3286)

### ca-2023-ab-2013.md
22. CONFIRMED ERROR — timeline 2024-08-26 Senate vote "(Ayes 38. Noes 0.)"; actual 39-0 (same off-by-one pattern).

### ca-2023-ab-2655.md — CLEAN (quotes verified).

### ca-2023-ab-3030.md
23. CONFIRMED ERROR — narrative: Health committee vote 16-0 "April 10" (actual April 9) and P&CP 10-0 "April 24" (actual April 23) — report dates vs vote dates.
24. CONFIRMED ERROR — bogus hearing entry "AB 3030 (Calderon) – APCP Analysis" dated 2024-04-21 — it's an analysis document, not a hearing; APCP hearing was 4/23 (listed separately). Also dup hearing entries.
25. CONFIRMED ERROR — narrative attributes narrowing amendment to "Senate floor amendments"; actually Senate committee amendments (Health 6/26-27, Approps 8/15).

### ca-2023-ab-3286.md
- SUSPECTED — "Senate Appropriations hearing 6/24/2024" listed, but bill bypassed hearing via Rule 28.8. Misleading.

## CA batch 5 (sb-53, ab-1064, ab-1337)

### ca-2025-sb-53.md
26. CONFIRMED ERROR — Votes: spurious duplicate Senate concurrence "2025-09-12 S ... Passed 29-8" (real vote 09-13 only). Delete 09-12 row.
27. CONFIRMED ERROR — Newsom signing quote duplicated in statements (as "Gavin Newsom"/press and "Gov. Gavin Newsom"/signing — same quote/date/URL). Dedupe.
- SUSPECTED — 2025-07-16 APCP vote: timeline 9-0 vs Votes 10-0 (leginfo itself disagrees; add note or prefer roll call 10-0).
- SUSPECTED — law-brain commentary "SB 535's 10^26 threshold" typo for SB 53 (fix upstream law-brain page regulation-california-sb53-tfaia).

### ca-2025-ab-1064.md
28. CONFIRMED ERROR — Summary: "both developers and operators" — enrolled (vetoed) text imposes duties on operators only; also "directed at or likely to be used by children" reflects earlier framing. Rewrite summary sentence.

### ca-2025-ab-1337.md
29. CONFIRMED ERROR — page stale/self-contradictory: timeline+versions end 2026-05-06/2025-05-23 but attached .text.md is the 06/01/26 Amended Senate version; missing June 2026 actions (amended 6/1, hearings set/canceled through 6/25).
30. CONFIRMED ERROR — Summary mischaracterizes: frames as "state agencies" data-handling updates; core change is removing IPA exemption for LOCAL agencies from Jan 1, 2028 + PI definition revision. Rewrite summary.
- SUSPECTED — update_date 2025-06-02 vs latest_action_date 2026-05-06 (stale metadata).

## CA batch 6 (sb-354, sb-833, ab-979)

### ca-2025-sb-354.md
- SUSPECTED (staleness) — page ends 2026-05-27; real world: passed Asm Insurance 11-3 (6/17/26), now in Asm P&CP (hearing 7/1/26). Refresh needed.
- SUSPECTED — update_date 2025-06-04 predates latest_action_date 2026-05-27.

### ca-2025-sb-833.md
31. CONFIRMED ERROR — Summary overstates: applies only to STATE-AGENCY operators (§8954.50(g)), and §8954.51(a)(2)(B) allows periodic after-the-fact review instead of pre-execution approval. Rewrite.

### ca-2025-ab-979.md
32. CONFIRMED ERROR — Irwin "related" statement + CalMatters media item dated 2025-10-01; article published 2025-10-09. Fix both dates. (Quote itself verbatim/attributed OK.)

## CA batch 1 (sb-942, ab-801, ab-947, ab-1008)

### ca-2023-sb-942.md — CLEAN (all quotes verified).
- MINOR — 2024-08-29 Becker statement source_type: CREC (should be state label).

### ca-2023-ab-801.md
33. CONFIRMED ERROR — narrative: Senate Judiciary "(also 7–0)" on June 11, 2024 — actual 11-0 (timeline/Votes correct).
34. CONFIRMED ERROR — timeline 2024-08-28 Senate vote "(Ayes 38. Noes 0.)"; actual 39-0 (off-by-one pattern again).

### ca-2023-ab-947.md
- SUSPECTED — Senate floor 2023-09-05: narrative 39-0 vs timeline 38-0 (leginfo history says 38, roll call 39 w/ add-on). Note discrepancy.
- MINOR — hearings[0] chamber: House → Assembly.

### ca-2023-ab-1008.md — CLEAN (quotes verified; trivial 10-09 vs 10-10 statement-date nit).

## CA batch 4 (sb-362, sb-793, sb-1223)

### ca-2023-sb-362.md
35. CONFIRMED ERROR — narrative: APCP "voted 7-0 on June 26, 2023" — actual June 27 (per page's own timeline/votes/hearings).
36. CONFIRMED ERROR — narrative: Sept 2023 Approps amendments "deferred the portal's launch to August 1, 2026" — portal must be established by Jan 1, 2026; Aug 1, 2026 is when brokers must begin accessing it. Conflated deadlines.
- SUSPECTED — "principal coauthors" label: leginfo lists only Wiener as principal coauthor; Min/Gabriel/Hart/Lowenthal/Wicks are coauthors.

### ca-2023-sb-793.md
37. CONFIRMED ERROR — narrative: "Judiciary Committee approved it on April 21, 2023" — actual April 25 (4/21 = analysis date).
38. CONFIRMED ERROR — narrative: "Appropriations (August 14, 2023)" — actual August 16 (8/14 = analysis date).
39. CONFIRMED ERROR — narrative sequencing chronologically impossible ("After Senate amendments on April 10 and April 17... heard on April 12").
- SUSPECTED — Valencia called "principal coauthor"; leginfo lists as regular coauthor.

### ca-2023-sb-1223.md
40. CONFIRMED ERROR — narrative: "first dedicated neural-data privacy statute enacted anywhere in the United States" — Colorado HB 24-1058 (signed 2024-04-17) was first; CA second. Reframe.
41. CONFIRMED ERROR — quote transcription: "neurtechnology" (wiki-introduced typo inside verbatim quote; source says "neurotechnology"). Fix statements[0] + body.

## WA batch (wa-2019-hb-1071, wa-2023-hb-1155)

### wa-2019-hb-1071.md
42. CONFIRMED ERROR — Summary: "AG notification is required when 500 or more Washington residents are affected" — statute says MORE THAN 500 (501+). Fix Summary.

### wa-2023-hb-1155.md
43. CONFIRMED ERROR — narrative: Senate amendments "extended consumer-request response timelines to 45 days" — 45 days was already in the House-passed bill; Senate merely clarified authentication doesn't extend it. Senate amendments actually added phased compliance dates + JLARC review.
- SUSPECTED — narrative attributes changes to L&J Committee 3/22 action; enacted changes rode the Senate floor striking amendment (committee amendment NOT adopted per timeline).
- Both quotes verified verbatim. Everything else OK.

## VA batch (hb-381, hb-714, hb-2024, sb-1087)

### va-2022-hb-381.md — CLEAN.
### va-2022-hb-714.md
44. CONFIRMED ERROR — Summary: claims bill "codifies the AG's pre-suit cure process" — cure process pre-existed in 2021 VCDPA §59.1-584(B). HB 714 actually: expands nonprofit exemption (political orgs, some 501(c)(4)), repeals Consumer Privacy Fund §59.1-585, redirects penalties to revolving trust fund. Rewrite Summary last sentence.

### va-2023-hb-2024.md
45. CONFIRMED ERROR — Summary materially mischaracterizes enacted law: (1) only "the Commonwealth" (state agencies/subdivisions), NOT any person/website, barred from publication after demand; (2) no immediate-family coverage; (3) added penalty is CRIMINAL (Class 6 felony, 6-mo mandatory minimum), not civil. Also adds judges/magistrates to address-confidentiality eligibility. Rewrite Summary.
46. CONFIRMED ERROR — Full Text: HB2024H2 (2023-03-27) labeled "Conference Sub"; actually Governor's substitute (no conference occurred).

### va-2023-sb-1087.md — CLEAN.

## NY batch (all 12 pages)

### ny-2019-a-5635.md (SHIELD Act)
47. CONFIRMED ERROR — narrative: Senate passed S5575-A "42–21"; actual 42-20 (page's own Votes agree).
48. CONFIRMED ERROR — related_media "Consumer Protection Meeting" note: "5-2 favorable vote" — actual 5 aye + 2 aye-with-reservations, 0 nay (reported 7-0).
- SUSPECTED — timeline chamber tags scrambled on mixed A5635/S5575 rows (LegiScan artifact).

### ny-2021-a-3904.md — pre-flagged Cusick 2019 statement adjudicated OK (properly 'related'). MINOR: sponsor-memo statements source_type CREC.

### ny-2023-a-2896.md — CLEAN.
### ny-2023-a-7364.md — CLEAN.

### ny-2023-s-2659.md
49. CONFIRMED ERROR — narrative: "no recorded opposition at any stage"/"unanimous throughout" — contradicted by 60-1 (2023 Senate) and 140-5 (2024 Assembly).

### ny-2023-s-7676.md
50. CONFIRMED ERROR — narrative: initial 2023-10-02 referral "to the Judiciary Committee" — actually Rules; Judiciary on 2024-01-03.

### ny-2023-s-7694.md (SAFE for Kids)
51. CONFIRMED ERROR — narrative + YouTube related_media note attribute Chapter 120 to both S7694A and S7695B; S7695B is Chapter 121.
- SUSPECTED — "four members recording reservations" detail unverified.

### ny-2023-s-7695.md — CLEAN.
### ny-2025-a-3265, a-4947, a-9642, s-9088 — CLEAN.

## IL batch C (il-2025-hb-3041, hb-3720, hb-4980) — CLEAN
- MINOR (hb-4980) — Summary says "meaningful human control"; statutory standard is "meaningful and continuing human review". Tighten wording.
- NOTE — hb-3720/hb-4980 .text.md extractions missing bill page 1 (Docling artifact).

## TX batch (all 13 pages)

### tx-2019-sb-936.md — CLEAN (trivial enrolled-date discrepancy 5/22 vs 5/25 internal).
### tx-2021-hb-3746.md — CLEAN (trivial enrolled-date discrepancy).

### tx-2021-sb-15.md
52. CONFIRMED ERROR — narrative: "House Transportation Committee, chaired by Rep. Phil King" — chair was Terry Canales; King was House sponsor + conference chair.
53. CONFIRMED ERROR — narrative: agencies "chiefly TxDOT and Parks & Wildlife" — actually Texas Department of MOTOR VEHICLES (and TPWD); TxDOT not in bill.
- SUSPECTED — Votes section duplicates 2021-04-14 Senate votes (4 rows for 2 votes).

### tx-2021-sb-2116.md
54. CONFIRMED ERROR — narrative: "filed... on April 1, 2021" — filed March 12, 2021 (April 1 = first reading/referral).
55. CONFIRMED ERROR — narrative: "six Senate cosponsors" then lists SEVEN names (七 coauthors per TLO). Fix to "seven".

### tx-2023-hb-4.md
56. CONFIRMED ERROR — narrative: "received by the Senate on May 1, 2023" — received April 5; May 1 = Senate first reading/referral.

### tx-2023-sb-768.md
57. CONFIRMED ERROR — narrative: "reported favorably... on May 5, 2023" — reported April 26; May 5 = report filed with Coordinator.

### tx-2023-sb-2013.md
58. CONFIRMED ERROR — narrative: "Rep. Phil King also credited as a House author" — King was a SENATOR (SD-10) in 2023, Senate joint author.
59. CONFIRMED ERROR (substantive) — narrative describes the 2021 LSIPA (SB 2116) prohibition framework as what SB 2013 enacts; SB 2013 actually adds affiliate definition, ERCOT background checks/criminal-history access, Ch.113 compliance attestations, designated-country grid-equipment purchase reporting (5-yr lookback), registration suspension, AG audits. Also calling SB 2013 itself "the Lone Star Infrastructure Protection Act" is inaccurate (that's SB 2116). Rewrite narrative substance.

### tx-2023-sb-2105.md
60. CONFIRMED ERROR — narrative: "committee report was distributed May 22" — distributed May 20; May 22 = sent to Local & Consent Calendar.
- SUSPECTED — duplicate hearing entries (5 rendered for 3 events); one hearing cites History.aspx as source.

### tx-2025-hb-149.md — substance OK.
- SUSPECTED — duplicate hearings (5 for 3 events); History.aspx as hearing source; Votes repeats two 5/23 Senate votes.

### tx-2025-hb-150, hb-1709, hb-5118, sb-815 — CLEAN.
- NOTE: "Charles Creighton" is correct (legal name Charles Brandon Creighton).

## CO batch (all 13 pages)

### co-2019-hb-1197.md
61. CONFIRMED ERROR — Votes: "Adopt amendment L.006 — Failed 0-0" — L.006 was ADOPTED without objection (LegiScan artifact).

### co-2020-hb-1052.md — CLEAN.
### co-2021-sb-190.md (CPA) — CLEAN, quotes verified.

### co-2022-hb-1041.md
62. CONFIRMED ERROR — Votes: contradictory rows "Passed 23-9" and "Passed 24-9" for same 2022-03-04 Senate 3rd reading; official 24-9-2. Remove 23-9 row.

### co-2022-sb-171.md
63. CONFIRMED ERROR — narrative + related_media title: House 3rd reading "46-3-16" — actual 46 Yes, 16 No, 3 Excused (46-16-3); No/Excused transposed.

### co-2024-hb-1058.md — CLEAN.
### co-2024-hb-1104.md
- DEAD LINK — Senate 3rd reading roll-call URL leg.colorado.gov/content/hb24-1104vote55d98d → 404. Tally 33-0-2 itself correct.

### co-2024-hb-1130.md
- SUSPECTED — narrative "concurred, repassing 60-2" conflates concurrence (60-2) with repass (62-0).

### co-2024-sb-41.md — CLEAN.

### co-2024-sb-205.md (CO AI Act)
64. CONFIRMED ERROR — quote fidelity: Polis signing letter quote "tamper innovation" vs source "hamper innovation".
65. CONFIRMED ERROR (stale) — narrative's "February 1, 2026 effective date" outdated: delayed to June 30, 2026 by SB25B-004, then repealed/replaced by SB26-189 (eff. Jan 1, 2027) — SB24-205 never took effect as written. Page shows no indication.
- SUSPECTED — H.001 amendment failure attributed to 3rd reading May 8; actually failed 21-43 on May 7, 2nd reading.

### co-2026-hb-1139.md
66. CONFIRMED ERROR — narrative: Senate 3rd reading "32-0" — actual 32-3 (page's own Votes say 32-3).
- DATA — Versions/Full Text placeholder dates "1969-12-31" (also on hb-1210, sb-189).

### co-2026-hb-1210.md — CLEAN (vetoed 6/2/26 correct). DATA: "Chaptered" version label on vetoed bill.
### co-2026-sb-189.md — CLEAN, quotes verified.

## IL batch A (hb-2557, hb-2130, hb-2954)

### il-2019-hb-2557.md (AI Video Interview Act)
67. CONFIRMED ERROR — Summary describes the INTRODUCED bill, not enacted law: "in writing"/"written consent"/"facial expressions" were removed/changed by SFA1 (enacted: no writing requirement, "video interview"). Rewrite Summary from chaptered text.
- SUSPECTED — narrative implies Pappas/Costa Howard were cosponsors at introduction; added as chief co-sponsors 2019-05-29 (post-passage).
- DEAD LINKS — retired ILGA schemes: BillStatus.asp (sources/Enactment), /legislation/101/HB/*.htm (Versions/Full Text), votehistory PDFs.
- Votes/PA 101-0260/signing verified; quotes verified.

### il-2023-hb-2130.md (Insurance Data Security)
- SUSPECTED — narrative "passed both chambers without a single dissenting vote" in tension with 9-4-0 House committee vote (floor votes were indeed 107-0, 56-0).
- SUSPECTED — Votes labels 5/11 Senate vote "Motion in Senate"; was Third Reading.
- DEAD LINK — BillStatus.asp source URL.
- Everything else verified OK.

### il-2023-hb-2954.md (Doxing Act)
68. CONFIRMED ERROR — QUOTE MISATTRIBUTION: "Today marks a critical step forward..." attributed to Julie Morrison (verified:true) but source attributes it to David Goldenberg, ADL Midwest Regional Director. Reattribute or swap for Morrison's real quote.
- SUSPECTED — Summary is the synopsis of House Floor Amendment No. 1, not of the Act (ingestion artifact). Reader can't tell what the law does.
- SUSPECTED — narrative implies cosponsors/Morrison aboard at introduction; all added later.
- DEAD LINKS — BillStatus.asp, /legislation/103/HB/*.htm, votehistory PDFs.

### CROSS-CUTTING — ILGA site redesign retired BillStatus.asp, /legislation/<GA>/HB/*.htm, /legislation/votehistory/* URL schemes → 404 across IL pages. Systematic link-migration pass recommended (working: /ftp/legislation/.../BillStatus/HTML/, /documents/legislation/..., /Legislation/publicacts/view/...).

## FEDERAL batch (all 9 pages)

### 116-hr-7898.md — pre-flagged 2017/2024 items adjudicated CORRECT (properly 'related'; quotes verbatim). No change needed.
### 117-hr-2471.md — CLEAN (minor role-label inconsistency for Portman).
### 117-hr-7776.md — CLEAN.

### 118-hr-2670.md (FY2024 NDAA)
69. CONFIRMED ERROR — Votes: Senate conference-report vote (Record Vote 343) dated 2023-12-14 twice; actual 2023-12-13. Also duplicate rows (House roll 723 x2, Senate 343 x2).
70. CONFIRMED ERROR — narrative sequencing implies Senate acted after House; Senate cleared conference report Dec 13, before House Dec 14.
71. CONFIRMED ERROR — narrative "first [formal conference] in two years" — actually three years (last was FY2021 NDAA, Dec 2020).

### 118-hr-815.md — CLEAN.
### 119-hr-2808.md — CLEAN.

### 119-hr-9076.md
72. CONFIRMED ERROR — Summary claims "no bill text is available in the public record" — contradicted by page's own Full Text link and .text.md. Bill requires a court order for USPS mail covers. Rewrite Summary.

### 119-s-146.md (TAKE IT DOWN)
- SUSPECTED — 118th-Congress predecessor (S.4569) hearings/statements marked relation:on_bill (Cruz 2024-07-31 committee-vote statement etc.) inconsistent with 'related' convention used on 116-hr-7898. Reclassify to related.

### 119-s-1318.md — CLEAN.
- No dead links federal-wide.

## IL batch B (hb-3773, hb-4875, sb-2979)

### il-2023-hb-3773.md — substantively OK.
- SUSPECTED — "Chaptered" version dated 2024-08-14 vs PA date 2024-08-09 (LegiScan posting date).
- DEAD LINKS — full legacy ILGA family (BillStatus.asp, votehistory PDFs, /legislation/103/HB/*.htm, /legislation/publicacts/...).

### il-2023-hb-4875.md
73. CONFIRMED ERROR — narrative claims bill "voids contracts that substitute a digital replica... unless represented by counsel or union" — that's HB 4762 (Digital Voice and Likeness Protection Act), NOT HB 4875. Remove claim.
74. CONFIRMED ERROR — narrative: SFA3 added "extended 50-year post-mortem protection" — 50-year term existed since PA 90-747 (1999); amendment only inserted "or digital replica". Nothing extended.
75. CONFIRMED ERROR — narrative: "Reps. Mary Edly-Allen" as House cosponsor — she is a SENATOR, joined as Chief Senate Sponsor 2024-04-19.
- DEAD LINKS — same legacy ILGA families.

### il-2023-sb-2979.md (BIPA amendment)
76. CONFIRMED ERROR — narrative + hearing entries date Senate Judiciary 6-3 vote 2024-03-12; official record 2024-03-13 (page's own timeline agrees).
77. CONFIRMED ERROR — Cunningham 2024-05-16 quote duplicated in statements (identical quote/speaker/date/URL). Remove one.
- SUSPECTED — duplicate hearing entries (one event, two sources); WGEM article links SB 1506 not SB 2979 (shaky source); "Enrolled Bill Text" media links introduced-version filename.
- DEAD LINKS — same legacy ILGA families.

## VA batch 2024+2026 (hb-707, hb-638, hb-1257, hb-1261, hb-1521, sb-85)

### va-2024-hb-707.md
78. CONFIRMED ERROR — Summary: "known minors" — law applies to "known child" = under 13 (VCDPA definition), parental consent per COPPA. Fix to "known children (under 13)".
79. CONFIRMED ERROR — Full Text: HB707H2 labeled "Conference Sub"; actually Governor's substitute (no conference). Same error pattern as va-2023-hb-2024.
- SUSPECTED — Amendments entry "Senate amendments not adopted — [adopted]" self-contradictory; Senate adopted none.

### va-2026-hb-638 — CLEAN.
### va-2026-hb-1257 — SUSPECTED: duplicated timeline row (2026-02-02 action twice).
### va-2026-hb-1261 — SUSPECTED: "companion to H.B. 1257" — both are House bills, same patron; not a companion as term of art.
### va-2026-hb-1521 — CLEAN (some claims unverifiable, nothing contradicts).
### va-2026-sb-85 — SUSPECTED: update_date predates latest_action_date (stale field).

## VA/WA final batch (va-2019-hb-2396, va-2020-hb-1334, va-2021-hb-2307, wa-2025 x5)

### va-2019-hb-2396, va-2020-hb-1334 — CLEAN.

### va-2021-hb-2307.md (VCDPA)
80. CONFIRMED ERROR — Marsden natlawreview statement dated 2021-03-02; article dated 2021-02-17, context = introducing SB 1392 (Jan/Feb). Fix to on/before 2021-02-17.
81. CONFIRMED ERROR (minor) — Blue Virginia related_media dated 2021-03-02; published 2021-03-06.
- SUSPECTED — narrative ambiguity: narrates SB 1392's path after HB 2307's House passage without saying so; "Senate concurred in the House substitute 32-7 on Feb 19" easily misread as HB 2307 (whose sequence was reversed: House concurred 85-8). Reword for disambiguation.

### wa-2025-hb-1671 — CLEAN (stale update_date).
### wa-2025-hb-2157 — SUSPECTED: status "Introduced" vs timeline showing Rules X-file; 20 identical unlabeled amendment entries.
### wa-2025-hb-2481, sb-6120, sb-6312 — CLEAN.

## RECURRING PATTERNS (cross-jurisdiction)
A. Timeline Senate-floor vote counts off-by-one vs official roll call (CA: AB 1824, 1836, 2013, 2602, 801) — stale LegiScan snapshot before add-on votes.
B. Duplicate/phantom vote rows (CA AB 2273, SB 53; CO HB 1041, HB 1197; TX SB 15, HB 149; federal HR 2670; IL SB 2979 dup quote/hearings; TX SB 2105/HB 149 dup hearings).
C. Narrative "report/analysis date" confused with "vote/hearing date" (CA SB 793 x2, SB 362, AB 3030; TX SB 768, SB 2105, SB 2116, HB 4).
D. Summaries describing the INTRODUCED version, not the enacted law (IL HB 2557; VA HB 714, HB 2024, HB 707; WA HB 1071 threshold; CA SB 833, AB 1064, AB 1337; IL HB 2954 = amendment synopsis).
E. Wrong-law conflation in narratives (TX SB 2013 describes SB 2116; IL HB 4875 describes HB 4762; CA AB 1355 credits AB 874's change).
F. "Conference Sub" mislabel for Governor's substitutes (VA HB 2024, HB 707).
G. chamber: House for CA Assembly hearings (many pages); source_type: CREC for state committee analyses (CA AB 1130, AB 2273, SB 942; NY A 3904).
H. Dead-link families: ILGA legacy URL schemes (systematic, all IL pages); CO roll-call content URL (1).
I. Stale metadata: update_date < latest_action_date (CA SB 354, AB 1337; VA SB 85; WA HB 1671); CO 2026 pages epoch dates 1969-12-31.
J. Stale real-world status: CO SB24-205 effective-date superseded (delayed then repealed/replaced); CA SB 354 missing June 2026 actions; CA AB 1337 missing June 2026 actions.

## FINAL TALLY
- 257 pages checked structurally (0 errors); 113 bill pages substantively audited by 20+ agents; all statement-bearing pages quote spot-checked.
- ~81 confirmed errors, ~30 suspected issues, 1 confirmed dead link + systematic ILGA link rot.
- Quote checks: ~90 quotes fetched; all verbatim/attributed EXCEPT: IL HB 2954 misattribution (Morrison vs Goldenberg), CO SB24-205 "tamper"/"hamper", CA SB 1223 "neurtechnology" typo, CA SB 53 duplicated Newsom quote, IL SB 2979 duplicated Cunningham quote.
- federal (9 pages)
- CA 2019/2021 remaining batches (A, C?) — parent resumed 3 sub-auditors
- CA 2023/2025 — parent resumed 6 sub-auditors (21 pages)
- CO (13), IL remaining, NY (12), TX (13), VA/WA
