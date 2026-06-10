# FTC Enforcement Provisions Library backfill campaign (D100)

> Backfill of the 285 FTC consent orders (1997–2026) from the curated library at
> rafalsportfolio.me (`llms.txt` → `/data/ftc-cases.json` + provision shards) into
> `wiki/federal/enforcement/`. One tranche of ~25 cases per session, **newest first**.
>
> Per tranche: `uv run python scripts/stage_ftc_library.py --tranche <N> --size 25`,
> then one enforcement-extractor subagent per staged case (returns `in_scope` + `topics`
> + extractor fields in a single dispatch — see D100), assemble `classified.json`,
> `render-enforcement`, `reindex`, update this tracker, review gate, commit.
>
> Source snapshots cached under `data/external/` (gitignored? — they are derived; the
> committed product is the wiki pages). Snapshot generated 2026-03-27; cases newer than
> the snapshot arrive via the regular press-feed scan (`/zwiad-scan-enforcement`).

Ordering: `date_issued` desc, library `id` asc. 285 cases / 25 ≈ 12 tranches.
Tranche N = rows [(N-1)·25, N·25) of that ordering — stable as long as the cached
`ftc-cases.json` snapshot is unchanged. Already-tracked dockets are skipped at staging;
keyless duplicates (matters created from press releases without a docket) are resolved
via enforcement-matcher + deterministic confirm.

| Tranche | Date range (issued) | Status | staged | in | out | new | consolidated | Notes |
|--------:|---------------------|--------|-------:|---:|----:|----:|-------------:|-------|
| 1 | 2024-04 → 2026-01 | done | 25 | 24 | 1 | 23 | 1 | All items used local PDF-extraction text. In: GM/OnStar (connected-car data), Disney ($10M COPPA), Avast ($16.5M browsing-data), Marriott (3 breaches), BetterHelp ($7.8M health data), Ring, GoDaddy, Blackbaud, Verkada ($2.95M), Cerebral ($15M), Monument, 1Health.io/Vitagene (genetic), Cognosphere/Genshin ($20M COPPA), Aylo/Pornhub ($15M), Illusory/Nomad (crypto-bridge cyber), Vivint (FCRA white-paging), IntelliVision (AI facial-recognition bias claims — sole ai-topic case), Apitor, Roca Labs, + location-data quartet X-Mode/InMarket/Gravy/Mobilewalla. Out (1): **Aqua Finance** — extractor ruled deceptive financing with FCRA-furnisher counts incidental; BORDERLINE (Vivint's FCRA case is in) — flag for review. Consolidated (1): Illuminate → existing ftc-2026-illuminate-education (LLM match, deterministically confirmed; date_resolved preserved at 2026-06-05; matcher dispatch skipped for exact-name overlap=1.0, noted as deviation). New page ids are docket slugs (e.g. ftc-c-4828) per build_enforcement_id strong-key preference. |
| 2 | 2021-02 → 2024-03 | done | 25 | 23 | 2 | 23 | 0 | Local PDF-extraction text 25/25. In: **Rite Aid** (first FTC retail facial-recognition action — ai+privacy+cyber, 5-yr FR ban), **Amazon Alexa** ($25M COPPA), **Microsoft Xbox** ($20M COPPA), **Epic privacy unit** ($275M COPPA — record), GoodRx + Premom/Easy Healthcare (first HBNR actions), Flo Health, Zoom, Chegg, Drizly (CEO personally bound), CafePress, Global Tel*Link, **Everalbum** (ai — biometric/AI-training consent, face-embedding deletion), TransUnion Rental Screening ($15M FCRA), Instant Checkmate/TruthFinder ($5.8M), MyLife ($21M FCRA/ROSCA), OpenX ($7.5M), Ascension (GLBA Safeguards vendor-oversight), Edmodo, Kurbo/WW, Kuuhubb, ITMedia, Credit Bureau Center (borderline-in: FCRA free-report disclosure within a billing scheme — review). Out (2): **Epic billing unit** ($245M Fortnite dark-pattern billing — no data charge; note: same respondent two units, billing OUT / privacy IN) + **Fashion Nova** (review suppression). |
| 3–12 | ← 2021-02 | pending | | | | | | |
