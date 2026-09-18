#!/usr/bin/env python3
"""Minimal unittest: empty shadow validates; orphan shadow_leg fails."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validate  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=TZ)

SHADOW_FIELDS = [
    "shadow_id",
    "decided_at",
    "book",
    "lane",
    "market_family",
    "edge_grade",
    "paper_stake_usd",
    "offered_american",
    "offered_decimal",
    "fair_conservative",
    "gap_pp",
    "reason_not_taken",
    "status",
    "settled",
    "returned_usd",
    "settled_at",
    "notes",
    "created_at",
    "updated_at",
]
SHADOW_LEG_FIELDS = [
    "leg_id",
    "shadow_id",
    "game_id",
    "kickoff_at",
    "away_team",
    "home_team",
    "market",
    "side",
    "line_at_take",
    "price_at_take",
    "american_price_at_take",
    "decimal_price_at_take",
    "closing_data_available",
    "closing_line",
    "closing_price_american",
    "closing_price_decimal",
    "clv_no_vig",
    "result",
    "notes",
]


def _write_shadow(
    dirpath: Path, shadow: list[dict], shadow_legs: list[dict]
) -> tuple[Path, Path]:
    sp = dirpath / "shadow.csv"
    lp = dirpath / "shadow_legs.csv"
    with sp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHADOW_FIELDS)
        w.writeheader()
        for row in shadow:
            w.writerow({k: row.get(k, "") for k in SHADOW_FIELDS})
    with lp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHADOW_LEG_FIELDS)
        w.writeheader()
        for row in shadow_legs:
            w.writerow({k: row.get(k, "") for k in SHADOW_LEG_FIELDS})
    return sp, lp


class TestShadowValidate(unittest.TestCase):
    def test_empty_shadow_validates(self) -> None:
        """Header-only shadow + shadow_legs → OK (no fake PASS rows)."""
        with tempfile.TemporaryDirectory() as tmp:
            sp, slp = _write_shadow(Path(tmp), [], [])
            # Also need tickets/legs for main(); use repo data or empty headers.
            tp = Path(tmp) / "tickets.csv"
            lp = Path(tmp) / "legs.csv"
            tp.write_text(
                "ticket_id,placed_at,book,lane,market_family,stake_usd,"
                "to_win_usd,payout_usd,american_price,decimal_price,"
                "edge_grade_at_placement,stake_vs_grade,status,settled,"
                "returned_usd,settled_at,notes,created_at,updated_at\n",
                encoding="utf-8",
            )
            lp.write_text(
                "leg_id,ticket_id,game_id,kickoff_at,away_team,home_team,"
                "market,side,line_at_take,price_at_take,american_price_at_take,"
                "decimal_price_at_take,closing_data_available,closing_line,"
                "closing_price_american,closing_price_decimal,clv_no_vig,"
                "result,notes\n",
                encoding="utf-8",
            )
            code = validate.main(tp, lp, now=NOW, shadow_path=sp, shadow_legs_path=slp)
            self.assertEqual(code, 0)

            errors, debt = validate.validate(
                [],
                [],
                now=NOW,
                shadow=validate.load_csv(sp),
                shadow_legs=validate.load_csv(slp),
            )
            self.assertEqual(errors, [])
            self.assertEqual(debt, 0)

    def test_orphan_shadow_leg_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orphan = {
                "leg_id": "sl1",
                "shadow_id": "missing-shadow",
                "game_id": "2026_02_DET_BUF",
                "kickoff_at": "2026-09-17T20:15:00-04:00",
                "away_team": "DET",
                "home_team": "BUF",
                "market": "spread",
                "side": "BUF",
                "line_at_take": "-5.5",
                "price_at_take": "-110",
                "american_price_at_take": "-110",
                "closing_data_available": "true",
                "result": "pending",
                "notes": "",
            }
            sp, slp = _write_shadow(Path(tmp), [], [orphan])
            errors, _ = validate.validate(
                [],
                [],
                now=NOW,
                shadow=validate.load_csv(sp),
                shadow_legs=validate.load_csv(slp),
            )
            self.assertTrue(
                any("orphan shadow_id" in e for e in errors),
                errors,
            )

    def test_paper_stake_must_be_ten(self) -> None:
        row = {
            "shadow_id": "s1",
            "decided_at": "2026-09-17T10:00:00-04:00",
            "book": "DK",
            "lane": "TNF",
            "edge_grade": "PASS",
            "paper_stake_usd": "25",
            "reason_not_taken": "pass_edge",
            "status": "open",
            "notes": "",
        }
        errors, _ = validate.validate(
            [],
            [],
            now=NOW,
            shadow=[row],
            shadow_legs=[],
        )
        self.assertTrue(
            any("paper_stake_usd must be 10" in e for e in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
