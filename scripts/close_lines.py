#!/usr/bin/env python3
"""Refresh closing lines — Tuesday after week final ONLY.

Usage: python scripts/close_lines.py --refresh

Never invent closes for anytime_td / first_td.
Stub: implement against nflverse/gsis once wired; until then exit with guidance.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh closing_* columns (Tue after week final only)",
    )
    args = p.parse_args()
    if not args.refresh:
        print("Pass --refresh. Run only Tuesday after the week is final.")
        return 2
    print(
        "close_lines.py: stub — wire nflverse/gsis closes here. "
        "Skip anytime_td/first_td forever (closing_data_available=false)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
