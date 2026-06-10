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

**⚠ Date caveat (verification, 2026-06-10):** the library's `date_issued` is month-precision
with a day-15 placeholder, so all `date_filed`/`date_resolved` values from this campaign are
approximate by construction. Worse, in ~4 of 20 verified cases the library month tracked a
*later* FTC press item rather than the order itself (Avast → refund-claims item +1yr;
LifeLock → refund mailing +4yr; Ashley Madison → FTC award item +9mo; BetterHelp → +1yr).
Substance (penalties, recipients, order terms, allegations) verified 20/20 correct against
FTC.gov. Fixed pages: Avast, LifeLock, Ashley Madison, Rite Aid, BetterHelp, Marriott
(+Equifax $125M-trigger wording). **Full date audit (2026-06-10):** all ~112 rendered
library cases date-checked against FTC.gov; 12 further corrections applied (Roca Labs
→2018/2019, Vivint →2021-04, 1Health.io →2023, Ring →2023-05, CafePress →2022, Everalbum
→2021-05, Credit Bureau Center →2021/2023, EMP Media →2018, Office Depot →2019-03, Jerk
→2017-11, Vipvape →2016-06, LabMD →2016-07). Overall date-error rate ~16/112 (14%), always
the same failure mode: library month tracks a later refund/claims/appellate/award press
item. Substance error rate: 0/20 sampled. **Tranches 7+ must include one date-audit web
agent per tranche before the review gate.** Borderlines accepted as-is: ReadyTech (Oct vs
Nov 2018), IDmission (Nov vs Oct 2018), LeapLab (Feb vs Mar 2016) — within ±1 month.

Ordering: `date_issued` desc, library `id` asc. 285 cases / 25 ≈ 12 tranches.
Tranche N = rows [(N-1)·25, N·25) of that ordering — stable as long as the cached
`ftc-cases.json` snapshot is unchanged. Already-tracked dockets are skipped at staging;
keyless duplicates (matters created from press releases without a docket) are resolved
via enforcement-matcher + deterministic confirm.

| Tranche | Date range (issued) | Status | staged | in | out | new | consolidated | Notes |
|--------:|---------------------|--------|-------:|---:|----:|----:|-------------:|-------|
| 1 | 2024-04 → 2026-01 | done | 25 | 24 | 1 | 23 | 1 | All items used local PDF-extraction text. In: GM/OnStar (connected-car data), Disney ($10M COPPA), Avast ($16.5M browsing-data), Marriott (3 breaches), BetterHelp ($7.8M health data), Ring, GoDaddy, Blackbaud, Verkada ($2.95M), Cerebral ($15M), Monument, 1Health.io/Vitagene (genetic), Cognosphere/Genshin ($20M COPPA), Aylo/Pornhub ($15M), Illusory/Nomad (crypto-bridge cyber), Vivint (FCRA white-paging), IntelliVision (AI facial-recognition bias claims — sole ai-topic case), Apitor, Roca Labs, + location-data quartet X-Mode/InMarket/Gravy/Mobilewalla. Out (1): **Aqua Finance** — extractor ruled deceptive financing with FCRA-furnisher counts incidental; BORDERLINE (Vivint's FCRA case is in) — flag for review. Consolidated (1): Illuminate → existing ftc-2026-illuminate-education (LLM match, deterministically confirmed; date_resolved preserved at 2026-06-05; matcher dispatch skipped for exact-name overlap=1.0, noted as deviation). New page ids are docket slugs (e.g. ftc-c-4828) per build_enforcement_id strong-key preference. |
| 2 | 2021-02 → 2024-03 | done | 25 | 23 | 2 | 23 | 0 | Local PDF-extraction text 25/25. In: **Rite Aid** (first FTC retail facial-recognition action — ai+privacy+cyber, 5-yr FR ban), **Amazon Alexa** ($25M COPPA), **Microsoft Xbox** ($20M COPPA), **Epic privacy unit** ($275M COPPA — record), GoodRx + Premom/Easy Healthcare (first HBNR actions), Flo Health, Zoom, Chegg, Drizly (CEO personally bound), CafePress, Global Tel*Link, **Everalbum** (ai — biometric/AI-training consent, face-embedding deletion), TransUnion Rental Screening ($15M FCRA), Instant Checkmate/TruthFinder ($5.8M), MyLife ($21M FCRA/ROSCA), OpenX ($7.5M), Ascension (GLBA Safeguards vendor-oversight), Edmodo, Kurbo/WW, Kuuhubb, ITMedia, Credit Bureau Center (borderline-in: FCRA free-report disclosure within a billing scheme — review). Out (2): **Epic billing unit** ($245M Fortnite dark-pattern billing — no data charge; note: same respondent two units, billing OUT / privacy IN) + **Fashion Nova** (review suppression). |
| 3 | 2020-01 → 2021-02 | done | 25 | 23 | 2 | 23 | 0 | Local PDF-extraction text 25/25. In: **Retina-X** (landmark stalkerware action), **Tapplock** (IoT security claims), **InfoTrax** (B2B processor, 17 undetected intrusions), **Office Depot** ($25M fake malware-detection scans — cyber), **EMP Media/MyEx.com** (revenge-porn site — NCII precursor to TAKE IT DOWN Act), SkyMed (fake HIPAA seal + breach cover-up), Zoom-era cluster…AppFolio ($4.25M FCRA tenant screening), Midwest Recovery ($24.3M debt parking), Kohl's (FCRA 609(e) ID-theft records), HyperBeard ($4M COPPA), Mortgage Solutions (Yelp doxxing of customer credit/health data), Miniclip (COPPA safe-harbor claim), + the Jan-2020 **Privacy Shield misrepresentation sweep** (214 Technologies/Trueface.ai [ai], Thru, TDARX, Medable, LotaData, Incentive Services, Global Data Vault, DCR Workforce, RagingWire, T&M, Ortho-Clinical). Out (2): **Alliance Security** (recidivist telemarketing/DNC; FCRA credit pulls incidental — BORDERLINE, flag for review) + **BoostMyScore** (credit piggybacking, CROA/TSR). |
| 4 | 2018-09 → 2020-01 | done | 25 | 22 | 3 | 22 | 0 | Local PDF-extraction text 25/25. In: **Facebook** (20-yr order + record $5B penalty; Cambridge Analytica fallout — penalty figure annotated from the accompanying stipulated order, not the consent-order text), **Equifax** ($425M, 147M consumers), **Google/YouTube** ($170M COPPA), **Cambridge Analytica** itself (D09383 — algorithm-deletion precedent) + **Nix/Kogan individual orders** (C-4693/4694, separate page), **Musical.ly/TikTok** ($5.7M COPPA), **Uber** (2016 breach concealment), **D-Link** (litigated IoT security case, filed 2017 resolved 2019), LifeLock ($100M), Unrollme, BLU Products (ADUPS China firmware), ClixSense, DealerBuilt (GLBA), UNIXIZ/i-Dressup, RealPage ($3M FCRA matching accuracy), + Privacy Shield cluster (Click Labs, SecurTest, VenPath, SmartStart, ReadyTech, mResource, IDmission). Out (3): Innovative Paycheck + Integrated Flight (fake-document mills) + Apartment Hunters (rental-listing scam). |
| 5 | 2015-12 → 2018-05 | done | 25 | 25 | 0 | 25 | 0 | Local PDF-extraction text 25/25; first 100%-in-scope tranche. In: **Wyndham** (landmark 3rd Cir. Section-5 data-security authority), **LabMD** (litigated adjudication; status marked "vacated on appeal (11th Cir. 2018)" — appellate note annotated beyond order text), **Ashley Madison/Ruby** ($8.75M), **VIZIO** ($2.5M ACR smart-TV — precedent for the 2026 TX/Netflix suit, cross-noted), **Lenovo/Superfish** (MITM adware), **VTech** ($650K COPPA), **PayPal/Venmo** (GLBA), **Uber-era**: Turn (Verizon supercookies), InMobi ($4M location+COPPA), Oracle (Java updates), ASUS (router security), TaxSlayer (GLBA credential stuffing), Henry Schein ($250K fake encryption), Practice Fusion (health reviews), **Craig Brittain** (revenge-porn — with EMP Media forms the pre-TAKE-IT-DOWN NCII lineage, cross-noted), Sears (2018 order modification), Prime Sites/Explore Talent ($500K COPPA), Jerk.com (amended order), LeapLab (data-broker fraud feed), Credit Protection Assn (FCRA furnisher), Upromise ($500K order violation), + Privacy Shield/CBPR trio (Tru, Md7, Decusoft, Vipvape). |
| 6 | 2014-08 → 2015-12 | done | 25 | 25 | 0 | 25 | 0 | Local PDF-extraction text 25/25; second 100%-in-scope tranche. In: **Snapchat** (ephemeral-messaging deception, 4.6M-user breach), **Nomi** (retail MAC-address tracking — first location-analytics vendor action), **Yelp** ($450K COPPA) + TinyCo ($300K COPPA) + Retro Dreamer ($300K) + LAI Systems ($60K) (the 2014-15 COPPA app wave), Sprint ($2.95M FCRA Risk-Based Pricing), PaymentsMD (covert health-data collection), GMR Transcription (vendor-oversight HIPAA claims), Tricolor ($82K FCRA furnisher), + the **Oct-2015 Safe Harbor sweep** (13 cases: SteriMed, Pinger, One Industries, NAICS, Just Bagels, Jubilant Clinsys, CA Skate-Line, IOActive, Inbox Group, Golf Connect, Forensics Consulting, Dale Jarrett, Contract Logix) + TES Franchising & American Intl Mailing (May-2015 Safe Harbor). Notable: Golf Connect & Contract Logix establish acquirer liability for inherited lapsed certifications. |
| 7–12 | ← 2014-08 | pending | | | | | | |
