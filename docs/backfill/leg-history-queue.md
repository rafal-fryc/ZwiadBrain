# Legislative-history follow-up queue

> Significant enacted laws flagged during the enacted-laws backfill (D85) for a later,
> **per-law-approved** `/zwiad-leg-history` pass. Leg-history is the expensive multi-subagent
> grounded-research flow and is **not** run during the backfill — it is run on demand, one law at
> a time, after you approve each. The `/zwiad-backfill-enacted[-state]` commands append rows here in
> their step 7.

**Flag a law when** it is a named Act, or otherwise high-salience (a major rewrite, broad scope,
landmark privacy/AI/cyber statute). Skip routine/minor enactments — the queue is for the laws whose
interpretation a sourced legislative history materially helps.

**Status:** `flagged` → `approved` (you OK'd a leg-history run) → `done` (leg-history rendered).

## Queue

| Wiki id | Title | Jurisdiction | Why significant | Status | leg-history cmd |
|---------|-------|--------------|-----------------|--------|-----------------|
| 118-hr-815 | PL 118-50 (carries PADFAA + Protecting Americans from Foreign Adversary Controlled Applications Act / TikTok divestiture) | US | landmark data-broker + foreign-adversary-app statutes; high salience; rode an emergency-supplemental vehicle | done | /zwiad-leg-history 118/hr/815 |
| 117-hr-7776 | PL 117-263 / FY23 NDAA — carries the Daniel Anderl Judicial Security and Privacy Act (data-broker ban re: federal judges' info) | US | named data-broker/judicial-security Act; CAVEAT: the relevant history is the *standalone* Daniel Anderl bill, not the NDAA vehicle — leg-history keyed to 117/hr/7776 would surface defense-bill history, low value | done | /zwiad-leg-history 117/hr/7776 |
| 116-hr-7898 | PL 116-321 — HITECH/HIPAA amendment ("HIPAA Safe Harbor"): cybersecurity-practice incentive in HIPAA enforcement + info-blocking investigation authority | US | company-facing health-data security/privacy statute; NOTE: narrow enforcement-discretion amendment (lower priority than a broad rewrite) | done | /zwiad-leg-history 116/hr/7898 |
| ca-2019-ab-1202 | AB 1202 (Ch. 753, 2019) — California Data Broker Registration law (Civ. Code §1798.99.80 et seq.) | US-CA | landmark, first-of-its-kind state data-broker registry; D88-core | done | /zwiad-leg-history ca/ab-1202 |
| ca-2021-ab-2273 | AB 2273 (Ch. 320, 2022) — California Age-Appropriate Design Code Act (Civ. Code Title 1.81.47) | US-CA | landmark children's-privacy / online-design statute; high salience (later NetChoice litigation) | done | /zwiad-leg-history ca/ab-2273 |
| ca-2023-sb-362 | SB 362 (Ch. 709, 2023) — the DELETE Act (single accessible data-broker deletion mechanism) | US-CA | landmark data-broker law; D88-core | done | /zwiad-leg-history ca/sb-362 |
| ca-2023-ab-2013 | AB 2013 (Ch. 817, 2024) — Generative AI training-data transparency (Civ. Code Title 15.2) | US-CA | first-of-its-kind GenAI training-data disclosure mandate | done | /zwiad-leg-history ca/ab-2013 |
| ca-2023-sb-1223 | SB 1223 (Ch. 887, 2024) — neural data added to CCPA sensitive personal information | US-CA | novel neural-data privacy first; high salience | done | /zwiad-leg-history ca/sb-1223 |
| ca-2023-ab-2655 | AB 2655 (Ch. 261, 2024) — Defending Democracy from Deepfake Deception Act (platform duties) | US-CA | named AI-election Act; platform-facing; notable litigation | done | /zwiad-leg-history ca/ab-2655 |
| ny-2019-a-5635 | A 5635 (Ch. 117, 2019) — NY SHIELD Act (breach notification + data-security safeguards on businesses) | US-NY | landmark state data-security statute; high salience | done | /zwiad-leg-history ny/a-5635 |

<!--
Example rows (delete once real entries land):
| 118-s-2073 | FAA Reauthorization Act of 2024 | US | named Act, broad scope | flagged | /zwiad-leg-history 118/s/2073 |
| ca-2019-ab-25 | California Consumer Privacy Act amendments | US-CA | landmark privacy statute | flagged | /zwiad-leg-history ca/AB25 |
-->
| ny-2023-s-7695 | S 7695 (Ch.?, 2024) — New York Child Data Protection Act | US-NY | landmark state children-data-protection statute | done | /zwiad-leg-history ny/s-7695 |
| tx-2021-sb-2116 | SB 2116 (2021) — Lone Star Infrastructure Protection Act (bars hostile-nation-owned companies from critical-infrastructure access contracts) | US-TX | named critical-infra security Act; first-of-its-kind state foreign-adversary infrastructure ban | done | /zwiad-leg-history tx/sb-2116 |
| tx-2023-hb-4 | HB 4 (2023) — Texas Data Privacy and Security Act (TDPSA) | US-TX | landmark comprehensive state consumer-privacy statute | done | /zwiad-leg-history tx/hb-4 |
| tx-2023-sb-2105 | SB 2105 (2023) — Texas data-broker registration law (SoS registry + security-program duty) | US-TX | D88-core data-broker registry statute | done | /zwiad-leg-history tx/sb-2105 |
| co-2021-sb-190 | SB21-190 — Colorado Privacy Act (CPA) | US-CO | landmark comprehensive state consumer-privacy statute (3rd in US); universal opt-out first | done | /zwiad-leg-history co/sb-190 |
| co-2024-sb-205 | SB24-205 — Colorado AI Act (Consumer Protections for Artificial Intelligence) | US-CO | FIRST comprehensive US state AI law; developer/deployer high-risk-AI duties; highest salience in the corpus | done | /zwiad-leg-history co/sb-205 |
| va-2021-hb-2307 | HB 2307 (2021) — Virginia Consumer Data Protection Act (VCDPA) | US-VA | SECOND comprehensive US state privacy law; template for the post-CCPA state wave | done | /zwiad-leg-history va/hb-2307 |
| wa-2023-hb-1155 | HB 1155 (2023) — My Health My Data Act | US-WA | first-of-its-kind consumer-health-data privacy law; private right of action; geofencing ban | done | /zwiad-leg-history wa/hb-1155 |
| il-2019-hb-2557 | HB 2557 (2019) — Artificial Intelligence Video Interview Act | US-IL | FIRST US law regulating AI in hiring | done | /zwiad-leg-history il/hb-2557 |
| il-2023-hb-3773 | HB 3773 (2024) — IL Human Rights Act amendment: discriminatory employer AI banned | US-IL | landmark employment-AI antidiscrimination law (eff. 2026) | done | /zwiad-leg-history il/hb-3773 |
| ny-2023-s-7694 | S 7694-A (2024) — SAFE for Kids Act (addictive feeds to minors) | US-NY | landmark platform-design/minors law; companion to tracked S 7695 | done | /zwiad-leg-history ny/s-7694 |
| va-2023-sb-1087 | SB 1087 (Ch. 526, 2023) — Virginia genetic data privacy (consumer genetic-data protections + civil penalty) | US-VA | novel state genetic-data-privacy statute; gap-scan 2026-07-02 (queue was stale) | done | /zwiad-leg-history va/1650572 |
| wa-2019-hb-1071 | HB 1071 (2019) — Washington data-breach notification expansion ("Protecting personal information") | US-WA | landmark WA data-security/breach-notification statute; gap-scan 2026-07-02 | done | /zwiad-leg-history wa/1136623 |
| 117-hr-2471 | PL 117-103 Division Y — CIRCIA (Cyber Incident Reporting for Critical Infrastructure Act of 2022) | US | landmark federal critical-infra incident-reporting mandate; CAVEAT: leg-history keyed to the omnibus surfaces appropriations history — the useful record is the standalone CIRCIA bills (S 2875 / HR 5440) | done | /zwiad-leg-history 117/hr/2471 |
| 119-s-146 | PL 119-12 — TAKE IT DOWN Act (NCII/deepfake ban + 48-hour platform removal duty, FTC-enforced) | US | landmark: first federal statute regulating AI-generated intimate imagery and platform takedown duties; active FTC enforcement since May 2026 (see ftc-2026-nudify-tool-operators) | done | /zwiad-leg-history 119/s/146 |

<!-- Law-brain-driven new-states privacy wave (backfilled 2026-07-02; comprehensive state privacy acts + notable named Acts). -->
| ct-2022-sb-6 | SB 6 (P.A. 22-15, 2022) — Connecticut Data Privacy Act (CTDPA) | US-CT | landmark comprehensive state consumer-privacy statute (5th in US) | done | /zwiad-leg-history ct/1585736 |
| or-2023-sb-619 | SB 619 (2023) — Oregon Consumer Privacy Act (OCPA) | US-OR | comprehensive state consumer-privacy statute; broad "personal data" + nonprofit reach | done | /zwiad-leg-history or/1647172 |
| de-2023-hb-154 | HB 154 (2023) — Delaware Personal Data Privacy Act (DPDPA) | US-DE | comprehensive state consumer-privacy statute; low applicability thresholds | done | /zwiad-leg-history de/1764243 |
| fl-2023-s-262 | SB 262 (2023) — Florida Digital Bill of Rights | US-FL | comprehensive privacy for large controllers + children-online + platform provisions | done | /zwiad-leg-history fl/1726624 |
| in-2023-sb-5 | SB 5 (2023) — Indiana Consumer Data Protection Act | US-IN | comprehensive state consumer-privacy statute (VA-model) | done | /zwiad-leg-history in/1648620 |
| ky-2024-hb-15 | HB 15 (Acts Ch. 72, 2024) — Kentucky Consumer Data Protection Act | US-KY | comprehensive state consumer-privacy statute | done | /zwiad-leg-history ky/1836575 |
| md-2024-hb-567 | HB 567 (2024) — Maryland Online Data Privacy Act (MODPA) | US-MD | comprehensive privacy with strongest-in-US data-minimization | done | /zwiad-leg-history md/1826294 |
| md-2024-hb-603 | HB 603 (2024) — Maryland Kids Code (Age-Appropriate Design) | US-MD | children's online design-code statute (AADC family; litigation-prone) | flagged | /zwiad-leg-history md/1826424 |
| mn-2023-hf-4757 | HF 4757 (2024) — Minnesota Consumer Data Privacy Act (MCDPA) | US-MN | comprehensive privacy w/ novel right to contest profiling; omnibus-vehicle CAVEAT | flagged | /zwiad-leg-history mn/1861147 |
| ne-2023-lb-1074 | LB 1074 (2024) — Nebraska Data Privacy Act | US-NE | comprehensive state consumer-privacy statute (TX-model); omnibus-vehicle CAVEAT | flagged | /zwiad-leg-history ne/1803810 |
| ri-2024-h-7787 | H 7787 (2024) — Rhode Island Data Transparency and Privacy Protection Act | US-RI | comprehensive state consumer-privacy statute; identical companion S 2500 also enacted | done | /zwiad-leg-history ri/1857250 |
| nj-2022-s-332 | S 332 (P.L.2023 c.266) — New Jersey Data Privacy Act | US-NJ | comprehensive state consumer-privacy statute; rulemaking authority | flagged | /zwiad-leg-history nj/1555075 |

<!-- Law-brain-driven tier B: remaining untracked states AL/PA/TN/UT (backfilled 2026-07-02). -->
| ut-2022-sb-227 | SB 227 (2022) — Utah Consumer Privacy Act (UCPA) | US-UT | landmark comprehensive state consumer-privacy statute (4th in US) | done | /zwiad-leg-history ut/1593499 |
| ut-2024-sb-149 | SB 149 (2024) — Utah Artificial Intelligence Policy Act (UAIPA) | US-UT | FIRST US state AI-specific consumer-protection law; generative-AI disclosure + AI sandbox | done | /zwiad-leg-history ut/1828750 |
| tn-2023-hb-1181 | HB 1181 (2023) — Tennessee Information Protection Act (TIPA) | US-TN | comprehensive state consumer-privacy statute; unique NIST-Privacy-Framework affirmative defense | flagged | /zwiad-leg-history tn/1688520 |
| tn-2023-hb-2091 | HB 2091 (Pub. Ch. 588, 2024) — ELVIS Act (voice/likeness right of publicity) | US-TN | landmark: first US law adding "voice" to the right of publicity w/ AI-tool secondary liability; NO FAKES Act analog | done | /zwiad-leg-history tn/1826894 |
| al-2026-hb-351 | HB 351 (2026) — Alabama Personal Data Protection Act (APDPA) | US-AL | comprehensive state consumer-privacy statute (21st in US); lowest 25,000-consumer threshold | flagged | /zwiad-leg-history al/2101947 |
| al-2024-hb-21 | HB 21 (2024) — Alabama Genetic Data Privacy Act | US-AL | state DTC-genetic-testing privacy statute (consent + deletion; AG-enforced) | flagged | /zwiad-leg-history al/1785848 |
| tn-2023-hb-1310 | HB 1310 (2023) — Tennessee Genetic Information Privacy Act | US-TN | state DTC-genetic-testing privacy statute | flagged | /zwiad-leg-history tn/1688672 |
