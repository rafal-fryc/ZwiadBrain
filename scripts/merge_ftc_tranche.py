"""Merge a staged FTC-library tranche with its extractor outputs into classified.json.

Joins data/runs/<run>/items/item-NN.json (staged candidates) with
data/runs/<run>/extracted/batch*.json (extended enforcement-extractor outputs keyed by
"index") and writes the render-enforcement input. Items the extractor ruled out of scope
are listed to stdout and omitted.

Usage:
  uv run python scripts/merge_ftc_tranche.py --run data/runs/<id> \
      [--match <index>:<matter_id>:<confidence> ...]

--match marks an item as an LLM-proposed consolidation into an existing keyless matter
(match_source="llm"); render-enforcement re-confirms it deterministically. When a match
is set, date_resolved is forced to null so the merge cannot regress a newer resolution
date already on the existing page (merge_current_state applies non-null values).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Any is confined to this alias: inputs are this campaign's own staged JSON.
JsonDict = dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--match", action="append", default=[],
                        help="<index>:<matter_id>:<confidence> LLM-match override")
    args = parser.parse_args()

    matches: dict[int, tuple[str, float]] = {}
    for spec in args.match:
        idx_s, matter_id, conf_s = spec.split(":")
        matches[int(idx_s)] = (matter_id, float(conf_s))

    extracted: dict[int, JsonDict] = {}
    for batch in sorted((args.run / "extracted").glob("batch*.json")):
        for entry in json.loads(batch.read_text(encoding="utf-8-sig")):
            extracted[entry["index"]] = entry

    classified: list[JsonDict] = []
    skipped: list[str] = []
    for item_path in sorted((args.run / "items").glob("item-*.json")):
        item: JsonDict = json.loads(item_path.read_text(encoding="utf-8-sig"))
        idx = int(item_path.stem.split("-")[1])
        ex = extracted.get(idx)
        if ex is None:
            skipped.append(f"{item_path.name}: NO EXTRACTOR OUTPUT (pending)")
            continue
        if not ex.get("in_scope"):
            skipped.append(f"{item_path.name}: out of scope ({item['company_name']})")
            continue
        matter_id, confidence = matches.get(idx, (None, 0.0))
        date_resolved = None if matter_id else ex.get("date_resolved")
        classified.append({
            "matter_id": matter_id,
            "match_source": "llm" if matter_id else "none",
            "match_confidence": confidence,
            "agency": item["agency"],
            "agency_slug": item["agency_slug"],
            "jurisdiction": item["jurisdiction"],
            "strong_key": item.get("strong_key"),
            "title": item["title"],
            "topics": ex["topics"],
            "respondent": ex.get("respondent"),
            "summary": ex.get("summary"),
            "background": ex.get("background"),
            "allegations": ex.get("allegations"),
            "outcome": ex.get("outcome"),
            "significance": ex.get("significance"),
            "action_type": ex.get("action_type"),
            "statutes": ex.get("statutes") or [],
            "penalties": ex.get("penalties"),
            "status": ex.get("status"),
            "date_filed": ex.get("date_filed"),
            "date_resolved": date_resolved,
            "development": {
                "date": ex.get("date_filed") or item.get("published"),
                "summary": ex["development_summary"],
                "source_url": item["url"],
            },
            "source_url": item["url"],
            "sources": {item["agency"]: item["url"]},
        })

    out = args.run / "classified.json"
    out.write_text(json.dumps(classified, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"merged {len(classified)} in-scope item(s) -> {out}")
    for s in skipped:
        print(f"  skipped {s}")


if __name__ == "__main__":
    main()
