"""Stage a tranche of FTC Enforcement Provisions Library cases for the enforcement pipeline.

The library (https://www.rafalsportfolio.me/llms.txt) is a curated snapshot of 285 FTC
consent orders (1997-2026) with docket numbers, FTC.gov case URLs, and per-case
provision summaries. This stager converts a tranche of those cases into per-item JSON
files that the interactive session feeds to the enforcement-extractor subagent, mirroring
the items/ layout used by /zwiad-scan-enforcement. It is deterministic and does no LLM work.

Inputs (cached snapshots under data/external/, fetched once by the session):
  - data/external/ftc-cases.json            (case database)
  - data/external/provisions/<topic>.json   (statutory provision shards)

Usage:
  uv run python scripts/stage_ftc_library.py --tranche 1 --size 25 [--out data/runs/<id>]

Cases are ordered newest-first (date_issued desc, id asc as tiebreak); tranche N covers
rows [(N-1)*size, N*size). Cases whose docket already appears on an existing wiki
enforcement page are skipped (idempotent re-runs). The wiki respondent list is written to
matters-shortlist.json so the session can run the matcher for keyless overlaps.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

# Any is confined to this alias: the script's inputs are external third-party JSON
# snapshots (rafalsportfolio.me) with no schema we control.
JsonDict = dict[str, Any]

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "data" / "external"
WIKI_ENFORCEMENT = ROOT / "wiki" / "federal" / "enforcement"
# Local mirror of the library's source-of-truth: per-case structured JSON (complaint
# factual background + counts, order provisions) extracted from the case PDFs.
LOCAL_CASES = Path(r"C:\Users\rafst\Documents\projectas\FTC\output_v2")

STATUTORY_SHARDS = [
    "section-5-only-provisions.json",
    "coppa-provisions.json",
    "fcra-provisions.json",
    "glba-provisions.json",
    "health-breach-notification-provisions.json",
    "tsr-provisions.json",
    "can-spam-provisions.json",
]


def load_cases() -> list[JsonDict]:
    # utf-8-sig: the cached snapshots are written by PowerShell, which emits a UTF-8 BOM.
    payload: JsonDict = json.loads((EXTERNAL / "ftc-cases.json").read_text(encoding="utf-8-sig"))
    return payload["cases"]


def load_provisions_by_case() -> dict[str, list[JsonDict]]:
    by_case: dict[str, list[JsonDict]] = {}
    for shard_name in STATUTORY_SHARDS:
        shard_path = EXTERNAL / "provisions" / shard_name
        if not shard_path.exists():
            continue
        shard: JsonDict = json.loads(shard_path.read_text(encoding="utf-8-sig"))
        for prov in shard["provisions"]:
            by_case.setdefault(prov["case_id"], []).append(
                {
                    "provision_number": prov.get("provision_number"),
                    "title": prov.get("title"),
                    "category": prov.get("category"),
                    "summary": prov.get("summary"),
                    "remedy_types": prov.get("remedy_types", []),
                }
            )
    return by_case


def existing_dockets_and_respondents() -> tuple[set[str], list[JsonDict]]:
    """Dockets + respondents from committed wiki enforcement pages (frontmatter scrape)."""
    dockets: set[str] = set()
    matters: list[JsonDict] = []
    if not WIKI_ENFORCEMENT.exists():
        return dockets, matters
    for page in WIKI_ENFORCEMENT.glob("*.md"):
        if page.name.endswith(".text.md"):
            continue
        text = page.read_text(encoding="utf-8")
        docket = re.search(r"^docket:\s*(\S.*)$", text, re.MULTILINE)
        respondent = re.search(r"^respondent:\s*(\S.*)$", text, re.MULTILINE)
        date_filed = re.search(r"^date_filed:\s*'?(\d{4}-\d{2}-\d{2})'?", text, re.MULTILINE)
        if docket:
            dockets.add(docket.group(1).strip().strip("'\""))
        matters.append(
            {
                "id": page.stem,
                "agency_slug": "ftc",
                "jurisdiction": "US",
                "respondent": respondent.group(1).strip().strip("'\"") if respondent else None,
                "date_filed": date_filed.group(1) if date_filed else None,
                "strong_key": docket.group(1).strip().strip("'\"") if docket else None,
            }
        )
    return dockets, matters


def load_local_case(case: JsonDict) -> JsonDict | None:
    """Per-case structured JSON from the local PDF-extraction mirror, when present."""
    name = case.get("source_filename")
    if not name:
        return None
    path = LOCAL_CASES / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_text_local(case: JsonDict, local: JsonDict) -> str:
    """Assemble the extractor's source text from the local complaint/order extraction."""
    complaint: JsonDict = local.get("complaint") or {}
    order: JsonDict = local.get("order") or {}
    counts: list[JsonDict] = complaint.get("counts") or []
    provisions: list[JsonDict] = order.get("provisions") or []
    lines = [
        f"FTC consent order: {case['company_name']}",
        f"Docket: {case.get('docket_number') or 'n/a'} | Issued: {case['date_issued']}",
        f"Legal authority: {case.get('legal_authority') or 'n/a'}",
        f"Statutory topics: {', '.join(case.get('statutory_topics', []))}",
        f"Practice areas: {', '.join(case.get('practice_areas', []))}",
        f"Industry sectors: {', '.join(case.get('industry_sectors', []))}",
        f"Order duration (years): {case.get('order_duration_years')}",
        "",
        f"Takeaway: {case.get('takeaway_brief') or ''}",
        "",
        "COMPLAINT — factual background:",
        str(complaint.get("factual_background") or "(not extracted)"),
        "",
        f"COMPLAINT — counts ({len(counts)}):",
    ]
    for c in counts:
        lines.append(f"  {c.get('count_number')}. {c.get('title')}")
        if c.get("representation"):
            lines.append(f"     {c['representation']}")
    lines += ["", f"ORDER — provisions ({len(provisions)}):"]
    for p in provisions:
        lines.append(f"  {p.get('provision_number') or '-'}. {p.get('title')} [{p.get('category')}]")
        if p.get("summary"):
            lines.append(f"     {p['summary']}")
    if order.get("duration"):
        lines += ["", f"ORDER — duration: {json.dumps(order['duration'], ensure_ascii=False)}"]
    return "\n".join(lines)


def build_text(case: JsonDict, provisions: list[JsonDict]) -> str:
    """Assemble the extractor's source text from the web provision shards (fallback
    when no local per-case JSON exists)."""
    lines = [
        f"FTC consent order: {case['company_name']}",
        f"Docket: {case.get('docket_number') or 'n/a'} | Issued: {case['date_issued']}",
        f"Legal authority: {case.get('legal_authority') or 'n/a'}",
        f"Statutory topics: {', '.join(case.get('statutory_topics', []))}",
        f"Practice areas: {', '.join(case.get('practice_areas', []))}",
        f"Industry sectors: {', '.join(case.get('industry_sectors', []))}",
        f"Order duration (years): {case.get('order_duration_years')}",
        "",
        f"Takeaway: {case.get('takeaway_brief') or ''}",
        "",
        "Complaint counts:",
        *[f"  - {c}" for c in case.get("complaint_counts", [])],
        "",
        f"Order provisions ({len(provisions)}):",
    ]
    for p in provisions:
        lines.append(f"  {p.get('provision_number') or '-'}. {p.get('title')} [{p.get('category')}]")
        if p.get("summary"):
            lines.append(f"     {p['summary']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tranche", type=int, required=True)
    parser.add_argument("--size", type=int, default=25)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cases = sorted(load_cases(), key=lambda c: (c["date_issued"], c["id"]), reverse=True)
    provisions_by_case = load_provisions_by_case()
    skip_dockets, matters = existing_dockets_and_respondents()

    start, end = (args.tranche - 1) * args.size, args.tranche * args.size
    tranche = cases[start:end]

    run_dir = args.out or ROOT / "data" / "runs" / (
        dt.datetime.now().strftime("%Y%m%dT%H%M%S") + f"-ftclib-t{args.tranche}"
    )
    items_dir = run_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    staged, skipped = 0, 0
    index_rows = []
    for n, case in enumerate(tranche):
        docket = case.get("docket_number")
        if docket and docket in skip_dockets:
            skipped += 1
            continue
        provisions = provisions_by_case.get(case["id"], [])
        local = load_local_case(case)
        text = build_text_local(case, local) if local else build_text(case, provisions)
        item = {
            "library_case_id": case["id"],
            "title": f"FTC consent order: {case['company_name']}",
            "agency": "FTC",
            "agency_slug": "ftc",
            "jurisdiction": "US",
            "url": case["ftc_url"],
            "published": case["date_issued"],
            "strong_key": docket,
            "matter_id": None,
            "company_name": case["company_name"],
            "statutory_topics": case.get("statutory_topics", []),
            "practice_areas": case.get("practice_areas", []),
            "text_source": "local-pdf-extraction" if local else "web-provision-shards",
            "text": text,
        }
        path = items_dir / f"item-{n:02d}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
        index_rows.append(
            {
                "file": path.name,
                "library_case_id": case["id"],
                "company_name": case["company_name"],
                "date_issued": case["date_issued"],
                "strong_key": docket,
                "statutory_topics": case.get("statutory_topics", []),
                "practice_areas": case.get("practice_areas", []),
            }
        )
        staged += 1

    (run_dir / "tranche-index.json").write_text(
        json.dumps(index_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "matters-shortlist.json").write_text(
        json.dumps(matters, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"tranche {args.tranche}: staged {staged} item(s), skipped {skipped} already-tracked "
        f"-> {run_dir}"
    )


if __name__ == "__main__":
    main()
