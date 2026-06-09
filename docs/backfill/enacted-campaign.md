# Enacted-laws backfill campaign tracker

> The source of truth for the prior-years **enacted-only** AI/privacy/cyber backfill
> (D84/D85; spec `docs/superpowers/specs/2026-06-08-enacted-laws-backfill-design.md`).
> One row = one **unit** = one (jurisdiction × period). Run a unit with
> `/zwiad-backfill-enacted <congress>` (federal) or `/zwiad-backfill-enacted-state <st> <year>`
> (state); each stops before commit for review. Update the row's **Status** and counts as you go.

**Status values:** `pending` → `in-review` (run done, awaiting your approval) → `done` (committed).

**Counts legend:** `enacted` = enacted laws discovered (full set; runs use `--classify-all` per D87,
so recall no longer pre-filters); `in` / `out` = classified in-scope / out-of-scope; `pages` = wiki
pages rendered; `flagged` = laws added to `leg-history-queue.md`.

> **D87 (run rule):** run every unit with `--classify-all` — the 118 calibration proved the recall
> pre-filter dropped ~80% of enacted laws and silently hid PL 118-50 (PADFAA + TikTok divestiture).
> ⚠ **Also pass `--limit <N>` ≥ the congress's enacted total** (e.g. `--limit 400`): the default
> `--limit 250` silently truncates the candidate set (`scanned[:limit]`). 117 has 362 enacted, so the
> default would have dropped 112. Check the "of N enacted laws" line in the fetch output.
> **Scope = company-facing obligations only (D86):** government-use surveillance/operations and
> omnibus appropriations/authorizations are OUT unless they carry a discrete company-facing
> AI/privacy/cyber provision. This rule is now encoded in `topics.yaml` (SCOPE preamble + criterion
> #4 + a government-operations disqualifier; commit 0639515), so the classifier applies it natively —
> no per-run prompt override needed.

## Federal (Congress.gov `/law/{congress}/pub`)

| Unit | Years | Status | enacted | in | out | pages | flagged | Notes |
|------|-------|--------|--------:|---:|----:|------:|--------:|-------|
| 116  | 2019–20 | done | 344 | 1 | 343 | 1 | 1 | classify-all (344, `--limit 400`). 1 in-scope: **HR 7898 / PL 116-321** (HITECH/HIPAA "Safe Harbor" — cyber-practice incentive in HIPAA enforcement; cyber+privacy). Excluded: CARES hr-748 (classifier confabulated a 290dd-2 provision absent from the CRS summary), IOGAN s-2904 (govt deepfake research), CAA-2021 hr-133 (govt AI CoE). NDAAs/CARES/FFCRA/CAA-2019/2020/2021/Nat-Resources all out. |
| 117  | 2021–22 | done | 362 | 1 | 361 | 1 | 1 | classify-all (362; needed `--limit 400` to beat the 250 output cap). 1 in-scope: **HR 7776 / PL 117-263** (FY23 NDAA) carries the **Daniel Anderl Act** (data-broker ban re: federal judges' info). Borderlines excluded per user (D88): Safe Connections hr-7132, Secure Equipment hr-3919, SBA-cyber s-1687. Big vehicles (NDAA/IIJA/CHIPS/IRA/ARPA/Approps-2023) all out as govt ops/funding. |
| 118  | 2023–24 | done | 274 | 1 | 272 | 1 | 1 | **classify-all** pass (D87): recall→52 + recall-hidden 221 = 273 classified (+1 already-tracked). 1 in-scope: **HR 815 / PL 118-50** (PADFAA data-broker ban + TikTok divestiture). Borderline hr-1568 (CBP strips PII from public manifests) EXCLUDED per D86 (govt duty) — flag for override. NDAA (hr-5009) & RISAA/FISA-702 (hr-7888) excluded per D86. Recall alone would have MISSED HR 815 (omnibus title). |

## States (LegiScan `getMasterList`, `status==4`)

Run `/zwiad-backfill-enacted-state <st> <year>`. The run-years below assume biennial sessions;
**confirm each state's actual sessions** (the command resolves `--year` → session, and errors if no
session covers the year). Annual-session states (e.g. NY, CO, VA) may have a distinct session per
year — add a row per session as confirmed. CA sessions are live-confirmed (1624=2019-20, 1791=2021-22,
2016=2023-24).

| Unit | Run year(s) | Status | enacted | in | out | pages | flagged | Notes |
|------|-------------|--------|--------:|---:|----:|------:|--------:|-------|
| ca / 2019-20 | 2019 | done | 14 | 9 | 5 | 9 | 1 | session 1624. **Recall** (not classify-all): 14 topical of ~870 enacted. 9 in: CCPA amendments (ab-25/713/874/1146/1281/1355/1564), data-breach (ab-1130), **data-broker registration (ab-1202)**. Out: ab-499 (state-agency SSN, govt), ab-1043 (campaign cyber), **ab-1215 (police facial recognition — govt-use, D86; landmark — flagged for review)**, sr-54/sjr-6 (resolutions). |
| ca / 2021-22 | 2021 | done | 10 | 3 | 7 | 3 | 1 | session 1791. Recall: 10 topical. 3 in: **AB 2273 Age-Appropriate Design Code Act**, AB 825 (genetic-data breach), AB 335 (CCPA vessel exemption). Out: govt-entity bills (EDD SSN, public-school cyber, local agencies, Cal-CSIC, state sector-cyber planning, Sec-GovOps deepfakes) + AR-5 resolution. |
| ca / 2023-24 | 2023 | done | 23 | 12 | 11 | 12 | 4 | session 2016. Recall: 23 topical. 12 in: CCPA (947/1008/1824/3286), **SB 362 DELETE Act**, **SB 1223 neural data**, **AB 2013 GenAI training-data transparency**, **AB 2655 deepfake-election platform duty** (D91), AB 3030 (health-AI disclosure), SB 793 (insurer privacy), AB 801 + AB 1971 (student/test privacy). Out: govt-AI/cyber (Dept of Tech ADS, CSU, Cal-CSIC, Sec-GovOps GenAI Accountability, school AI bills), AB 2355 (AI political-ad disclosure — election-actor, D91), 3 resolutions. |
| ny / 2019-20 | 2019 | done | 4 | 1 | 3 | 1 | 1 | After PHASE-27 fix (resolutions dropped, A/S deduped, recall broadened): recall→4. 1 in: **A 5635 NY SHIELD Act** (Ch.117/2019 — breach-notification + data-security on businesses; recall had missed it pre-fix). Out: AI study commission (a-1746), education biometric study/school ban (a-6787), budget Article VII (a-9508) — all govt. |
| ny / 2021-22 | 2021 | done | 6 | 0 | 6 | 0 | 0 | recall→6, 0 in-scope (NY passed no major company-facing privacy/AI/cyber law this session). All govt/edge: OITS biometric study, DFS literacy site, DEC/parking physical infra, 24h breach-notice-to-state-agencies. ⚠ BORDERLINE excluded: a-3904 critical-energy-infrastructure security (cyber 0.72) — terse metadata; flag for override. |
| ny / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |
| tx / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| tx / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
| tx / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |
| co / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| co / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
| co / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |
| va / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| va / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
| va / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |
| wa / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| wa / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
| wa / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |
| il / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| il / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
| il / 2023-24 | 2023 | pending | – | – | – | – | – | confirm session cadence |

## Progress

- Federal: **3 / 3 units done** (118: HR 815 / PADFAA+TikTok; 117: HR 7776 / Daniel Anderl Act; 116: HR 7898 / HIPAA Safe Harbor). ~980 enacted laws classified, 3 in-scope.
- States: 5 / 21 units done (PHASE-27 hardened big-state discovery). Method: **recall** per D89; **autonomous per-unit commits, stop only at borderlines** per D90.
  - ny/2019-20: 1 in-scope (A 5635 NY SHIELD Act). ny/2021-22: 0 in-scope (no major company-facing law; a-3904 borderline excluded).
  - ca/2019-20: 9 in-scope (CCPA cluster + AB 1202 data-broker registry).
  - ca/2021-22: 3 in-scope (AB 2273 AADC + AB 825 genetic-breach + AB 335 CCPA-vessel).
  - ca/2023-24: 12 in-scope (SB 362 DELETE Act, SB 1223 neural data, AB 2013 GenAI transparency, AB 2655 deepfake-election, AB 3030 health-AI, + CCPA/student/insurer). **CA complete (24 in-scope across 3 sessions).**
- Update these totals as units flip to `done`.
