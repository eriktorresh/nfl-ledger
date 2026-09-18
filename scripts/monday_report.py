#!/usr/bin/env python3
"""Monday scorecard / completed-week report from ledger CSVs.

Outcome ≠ evidence of grade. Stub prints open ticket counts until wired.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKETS = ROOT / "data" / "tickets.csv"


def main() -> int:
    with TICKETS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    open_n = sum(1 for r in rows if (r.get("status") or "").strip() == "open")
    settled_n = sum(1 for r in rows if (r.get("status") or "").strip() == "settled")
    print(f"monday_report: tickets={len(rows)} open={open_n} settled={settled_n}")
    print("Note: outcome is not evidence of grade quality.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
