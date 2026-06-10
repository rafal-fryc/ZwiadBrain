---
action_type: consent order
agency: FTC
allegations: 'The FTC alleged three counts: (1) unfair information security practices
  for failing to employ reasonable and appropriate measures to protect personal information;
  (2) data security misrepresentations by representing it implemented reasonable protections
  against unauthorized access when it did not; and (3) misrepresentations to school
  districts regarding breach notification, having promised 24- or 48-hour notice of
  incidents but delivering some notifications as late as October 2023, nearly two
  years after the breach.'
background: Illuminate Education served over 17 million students across more than
  5,200 school districts and made explicit contractual representations about encrypting
  student data and maintaining strong access controls. In practice, the company stored
  sensitive student personal information in plaintext, failed to disable credentials
  for a former employee who departed in 2018, and lacked adequate logging, monitoring,
  and identity access management. A threat actor exploited the stale credentials between
  December 2021 and January 2022 to breach Illuminate's AWS environment and exfiltrate
  SQL backups containing student records.
date_resolved: '2026-06-05'
developments:
- date: '2025-12-15'
  source_url: https://www.ftc.gov/legal-library/browse/cases-proceedings/222-3105-illuminate-education-inc-matter
  summary: FTC issued finalized consent order against Illuminate Education for inadequate
    student data security, breach of contractual security representations, and delayed
    breach notification affecting over 10.1 million students.
- date: '2026-06-05'
  source_url: https://www.ftc.gov/news-events/news/press-releases/2026/06/ftc-gives-final-approval-order-against-illuminate-settling-allegations-it-failed-secure-students
  summary: FTC gives final approval to modified consent order against Illuminate Education
    Inc. following public comment period, concluding settlement over data breach affecting
    10.1 million students.
id: ftc-2026-illuminate-education
jurisdiction: US
outcome: The finalized consent order imposes a 10-year compliance period. Illuminate
  must delete personal information no longer needed for contracted services, publish
  and follow a data retention schedule, implement a comprehensive written information
  security program with strict access controls and multi-factor authentication, obtain
  independent third-party security assessments biennially, have its CISO submit annual
  compliance certifications to the FTC, and notify the FTC of any future covered data
  incidents. The company is prohibited from misrepresenting its security practices
  or breach-notification timelines.
respondent: Illuminate Education Inc.
significance: This action extends FTC data security enforcement into the education
  technology sector and highlights the agency's willingness to charge companies for
  notification-timeline misrepresentations as a standalone deceptive practice. The
  nearly two-year delay in notifying affected students and districts underscores that
  post-breach conduct — not only the breach itself — is subject to FTC scrutiny under
  Section 5.
sources:
  FTC: https://www.ftc.gov/legal-library/browse/cases-proceedings/222-3105-illuminate-education-inc-matter
status: final
statutes:
- FTC Act Section 5
summary: The FTC charged Illuminate Education, an ed-tech company serving over 17
  million students, with failing to implement reasonable data security despite contractual
  promises to school districts, resulting in a 2021–2022 breach that exposed the personal
  information of more than 10.1 million students. The company also misrepresented
  that it would provide timely breach notifications but notified some districts nearly
  two years after discovery. A finalized consent order requires a decade-long information
  security program, independent biennial assessments, and data minimization obligations.
title: FTC Gives Final Approval to Order Against Illuminate Settling Allegations It
  Failed to Secure Students’ Personal Data
topics:
- privacy
- cyber
tracking: true
type: enforcement
---

## Summary

The FTC charged Illuminate Education, an ed-tech company serving over 17 million students, with failing to implement reasonable data security despite contractual promises to school districts, resulting in a 2021–2022 breach that exposed the personal information of more than 10.1 million students. The company also misrepresented that it would provide timely breach notifications but notified some districts nearly two years after discovery. A finalized consent order requires a decade-long information security program, independent biennial assessments, and data minimization obligations.

## Developments

- 2025-12-15 — FTC issued finalized consent order against Illuminate Education for inadequate student data security, breach of contractual security representations, and delayed breach notification affecting over 10.1 million students. — [source](https://www.ftc.gov/legal-library/browse/cases-proceedings/222-3105-illuminate-education-inc-matter)
- 2026-06-05 — FTC gives final approval to modified consent order against Illuminate Education Inc. following public comment period, concluding settlement over data breach affecting 10.1 million students. — [source](https://www.ftc.gov/news-events/news/press-releases/2026/06/ftc-gives-final-approval-order-against-illuminate-settling-allegations-it-failed-secure-students)

## Background

Illuminate Education served over 17 million students across more than 5,200 school districts and made explicit contractual representations about encrypting student data and maintaining strong access controls. In practice, the company stored sensitive student personal information in plaintext, failed to disable credentials for a former employee who departed in 2018, and lacked adequate logging, monitoring, and identity access management. A threat actor exploited the stale credentials between December 2021 and January 2022 to breach Illuminate's AWS environment and exfiltrate SQL backups containing student records.

## Allegations

The FTC alleged three counts: (1) unfair information security practices for failing to employ reasonable and appropriate measures to protect personal information; (2) data security misrepresentations by representing it implemented reasonable protections against unauthorized access when it did not; and (3) misrepresentations to school districts regarding breach notification, having promised 24- or 48-hour notice of incidents but delivering some notifications as late as October 2023, nearly two years after the breach.

## Outcome

The finalized consent order imposes a 10-year compliance period. Illuminate must delete personal information no longer needed for contracted services, publish and follow a data retention schedule, implement a comprehensive written information security program with strict access controls and multi-factor authentication, obtain independent third-party security assessments biennially, have its CISO submit annual compliance certifications to the FTC, and notify the FTC of any future covered data incidents. The company is prohibited from misrepresenting its security practices or breach-notification timelines.

## Significance

This action extends FTC data security enforcement into the education technology sector and highlights the agency's willingness to charge companies for notification-timeline misrepresentations as a standalone deceptive practice. The nearly two-year delay in notifying affected students and districts underscores that post-breach conduct — not only the breach itself — is subject to FTC scrutiny under Section 5.

## Sources

- [FTC](https://www.ftc.gov/legal-library/browse/cases-proceedings/222-3105-illuminate-education-inc-matter)
