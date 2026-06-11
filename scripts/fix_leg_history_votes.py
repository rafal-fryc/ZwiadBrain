"""One-off repair: re-fetch spine votes with the fixed recorded_votes()
(UTC->Eastern vote dates + roll-call dedup) and patch the staged render
inputs for the 2026-06-11 leg-history runs, so the pages can be re-rendered."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from zwiadbrain.sources.congress import CongressSource

RUNS: dict[str, str] = {
    "20260611T124300": "119/s/146",
    "20260611T124517": "116/hr/7898",
    "20260611T124524": "117/hr/2471",
    "20260611T124531": "117/hr/7776",
    "20260611T124537": "118/hr/815",
    "20260611T124542": "119/hr/2808",
}


def main() -> None:
    load_dotenv()
    source = CongressSource(os.environ["CONGRESS_API_KEY"])
    for run, native_id in RUNS.items():
        votes = [
            {
                "date": v.date.isoformat() if v.date else None,
                "chamber": v.chamber,
                "result": v.result,
                "roll_call_url": v.roll_call_url,
            }
            for v in source.recorded_votes(native_id)
        ]
        path = Path("data/runs") / run / "leghistory-research.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        before = len(doc["spine"]["votes"])
        doc["spine"]["votes"] = votes
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{native_id}: votes {before} -> {len(votes)}: "
              + "; ".join(f"{v['date']} {v['chamber']}" for v in votes))


if __name__ == "__main__":
    main()
