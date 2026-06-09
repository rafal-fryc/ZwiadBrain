# Enacted-laws backfill campaign tracker

> The source of truth for the prior-years **enacted-only** AI/privacy/cyber backfill
> (D84/D85; spec `docs/superpowers/specs/2026-06-08-enacted-laws-backfill-design.md`).
> One row = one **unit** = one (jurisdiction × period). Run a unit with
> `/zwiad-backfill-enacted <congress>` (federal) or `/zwiad-backfill-enacted-state <st> <year>`
> (state); each stops before commit for review. Update the row's **Status** and counts as you go.

**Status values:** `pending` → `in-review` (run done, awaiting your approval) → `done` (committed).

**Counts legend:** `enacted` = enacted laws discovered (post recall); `in` / `out` = classified
in-scope / out-of-scope; `pages` = wiki pages rendered; `flagged` = laws added to
`leg-history-queue.md`.

## Federal (Congress.gov `/law/{congress}/pub`)

| Unit | Years | Status | enacted | in | out | pages | flagged | Notes |
|------|-------|--------|--------:|---:|----:|------:|--------:|-------|
| 116  | 2019–20 | pending | – | – | – | – | – | |
| 117  | 2021–22 | pending | – | – | – | – | – | |
| 118  | 2023–24 | pending | – | – | – | – | – | |

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

- Federal: 0 / 3 units done.
- States: 0 / 21 units done (rows may grow if annual sessions need per-year units).
- Update these totals as units flip to `done`.
