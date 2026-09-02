from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "elise_investigator" / "app"
TESTS = ROOT / "tests"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(HERE))

from investigator import Investigator
from models import InvestigationRequest
from scenarios import LAMP, brightness_transition_scenario


PROBES = [
    {
        "name": "brightness-start-confirmed",
        "time": "2026-09-02T17:59:15+00:00",
        "value": 0,
        "attribute": "brightness",
    },
    {
        "name": "brightness-middle-same-transition",
        "time": "2026-09-02T18:01:31+00:00",
        "value": 16,
        "attribute": "brightness",
    },
    {
        "name": "brightness-late-same-transition",
        "time": "2026-09-02T18:02:30+00:00",
        "value": 17,
        "attribute": "brightness",
    },
]


async def run() -> int:
    parser = argparse.ArgumentParser(
        description="Replay a synthetic HA timeline against the checked-out Investigator revision."
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print one compact JSON object per probe.",
    )
    args = parser.parse_args()

    scenario = brightness_transition_scenario()
    rows = []
    for probe in PROBES:
        twin = scenario.at(probe["time"])
        investigator = Investigator(twin)
        result = await investigator.investigate(
            InvestigationRequest(
                entity_id=LAMP,
                observed_time=probe["time"],
                observed_value=probe["value"],
                attribute=probe["attribute"],
            )
        )
        payload = result.to_dict()
        row = {
            "probe": probe["name"],
            "revision_behavior": {
                "status": payload.get("status"),
                "event_type": payload.get("event_type"),
                "event_time": payload.get("event_time"),
                "observed": payload.get("observed"),
                "cause": payload.get("cause"),
                "answer_text": payload.get("answer_text"),
            },
        }
        rows.append(row)

    if args.compact:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
