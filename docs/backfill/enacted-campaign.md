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
> **Scope = company-facing obligations only (D86):** government-use surveillance/operations and
> omnibus appropriations/authorizations are OUT unless they carry a discrete company-facing
> AI/privacy/cyber provision. Inject this scope rule into the classifier prompt each run.

## Federal (Congress.gov `/law/{congress}/pub`)

| Unit | Years | Status | enacted | in | out | pages | flagged | Notes |
|------|-------|--------|--------:|---:|----:|------:|--------:|-------|
| 116  | 2019–20 | pending | – | – | – | – | – | |
| 117  | 2021–22 | pending | – | – | – | – | – | |
| 118  | 2023–24 | done | 274 | 1 | 272 | 1 | 1 | **classify-all** pass (D87): recall→52 + recall-hidden 221 = 273 classified (+1 already-tracked). 1 in-scope: **HR 815 / PL 118-50** (PADFAA data-broker ban + TikTok divestiture). Borderline hr-1568 (CBP strips PII from public manifests) EXCLUDED per D86 (govt duty) — flag for override. NDAA (hr-5009) & RISAA/FISA-702 (hr-7888) excluded per D86. Recall alone would have MISSED HR 815 (omnibus title). |

## States (LegiScan `getMasterList`, `status==4`)

Run `/zwiad-backfill-enacted-state <st> <year>`. The run-years below assume biennial sessions;
**confirm each state's actual sessions** (the command resolves `--year` → session, and errors if no
session covers the year). Annual-session states (e.g. NY, CO, VA) may have a distinct session per
year — add a row per session as confirmed. CA sessions are live-confirmed (1624=2019-20, 1791=2021-22,
2016=2023-24).

| Unit | Run year(s) | Status | enacted | in | out | pages | flagged | Notes |
|------|-------------|--------|--------:|---:|----:|------:|--------:|-------|
| ca / 2019-20 | 2019 | pending | – | – | – | – | – | session 1624 (confirmed) |
| ca / 2021-22 | 2021 | pending | – | – | – | – | – | session 1791 (confirmed) |
| ca / 2023-24 | 2023 | pending | – | – | – | – | – | session 2016 (confirmed) |
| ny / 2019-20 | 2019 | pending | – | – | – | – | – | confirm session cadence |
| ny / 2021-22 | 2021 | pending | – | – | – | – | – | confirm session cadence |
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

- Federal: 1 / 3 units done (118 done — 1 in-scope: HR 815 / PL 118-50).
- States: 0 / 21 units done (rows may grow if annual sessions need per-year units).
- Update these totals as units flip to `done`.
