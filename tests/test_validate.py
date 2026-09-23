#!/usr/bin/env python3
"""stdlib unittest for validate.py VERIFY rules."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import validate  # noqa: E402

TZ = ZoneInfo("America/New_York")
# Fixed "now" for deterministic tests: 2026-09-17 12:00 ET (before evening kickoffs).
NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=TZ)
TODAY = NOW.date()

TICKET_FIELDS = [
    "ticket_id",
    "placed_at",
    "book",
    "lane",
    "market_family",
    "stake_usd",
    "to_win_usd",
    "payout_usd",
    "american_price",
    "decimal_price",
    "edge_grade_at_placement",
    "stake_vs_grade",
    "status",
    "settled",
    "returned_usd",
    "settled_at",
    "notes",
    "created_at",
    "updated_at",
]
LEG_FIELDS = [
    "leg_id",
    "ticket_id",
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


def _write_csvs(dirpath: Path, tickets: list[dict], legs: list[dict]) -> tuple[Path, Path]:
    tp = dirpath / "tickets.csv"
    lp = dirpath / "legs.csv"
    with tp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TICKET_FIELDS)
        w.writeheader()
        for row in tickets:
            w.writerow({k: row.get(k, "") for k in TICKET_FIELDS})
    with lp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEG_FIELDS)
        w.writeheader()
        for row in legs:
            w.writerow({k: row.get(k, "") for k in LEG_FIELDS})
    return tp, lp


def _base_ticket(**over) -> dict:
    row = {
        "ticket_id": "t1",
        "placed_at": "2026-09-17T10:00:00-04:00",
        "book": "DK",
        "lane": "TNF",
        "market_family": "SGP",
        "stake_usd": "10",
        "edge_grade_at_placement": "PLAY",
        "stake_vs_grade": "agree",
        "status": "open",
        "settled": "false",
        "notes": "",
        "created_at": "2026-09-17T10:00:00-04:00",
        "updated_at": "2026-09-17T10:00:00-04:00",
    }
    row.update(over)
    return row


def _base_leg(**over) -> dict:
    row = {
        "leg_id": "l1",
        "ticket_id": "t1",
        "game_id": "2026-w2-det-buf",
        "kickoff_at": "2026-09-17T20:15:00-04:00",  # after NOW (12:00)
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
    row.update(over)
    return row


def _run(tickets, legs, now=NOW):
    with tempfile.TemporaryDirectory() as tmp:
        tp, lp = _write_csvs(Path(tmp), tickets, legs)
        return validate.validate(
            validate.load_csv(tp), validate.load_csv(lp), now=now
        )


class TestValidateVerify(unittest.TestCase):
    def test_fail_no_verify_date(self):
        # VERIFY token without VERIFY(YYYY-MM-DD):
        errors, _ = _run(
            [_base_ticket(notes="VERIFY: need book confirm")],
            [_base_leg()],
        )
        self.assertTrue(
            any("missing/malformed date" in e for e in errors),
            errors,
        )

    def test_fail_verify_older_than_7_days(self):
        old = (TODAY - timedelta(days=8)).isoformat()
        errors, _ = _run(
            [_base_ticket(notes=f"VERIFY({old}): leftover")],
            [_base_leg()],
        )
        self.assertTrue(
            any("more than 7 days" in e for e in errors),
            errors,
        )

    def test_fail_blank_placed_at_with_fresh_verify(self):
        errors, _ = _run(
            [
                _base_ticket(
                    placed_at="",
                    notes=f"VERIFY({TODAY.isoformat()}): placed_at unknown",
                )
            ],
            [_base_leg()],
        )
        self.assertTrue(
            any("missing placed_at" in e and "never excuses" in e for e in errors),
            errors,
        )

    def test_fail_blank_game_id_with_fresh_verify(self):
        errors, _ = _run(
            [_base_ticket()],
            [
                _base_leg(
                    game_id="",
                    notes=f"VERIFY({TODAY.isoformat()}): game_id TBD",
                )
            ],
        )
        self.assertTrue(
            any("missing game_id" in e and "never excuses" in e for e in errors),
            errors,
        )

    def test_fail_blank_prices_with_fresh_verify(self):
        errors, _ = _run(
            [_base_ticket()],
            [
                _base_leg(
                    price_at_take="",
                    american_price_at_take="",
                    notes=f"VERIFY({TODAY.isoformat()}): price TBD",
                )
            ],
        )
        self.assertTrue(
            any("missing price" in e and "never excuses" in e for e in errors),
            errors,
        )

    def test_pass_atd_blank_price_with_dated_verify_after_kickoff(self):
        after = datetime(2026, 9, 17, 21, 0, 0, tzinfo=TZ)
        errors, debt = _run(
            [_base_ticket()],
            [
                _base_leg(
                    market="anytime_td",
                    side="Nabers",
                    line_at_take="",
                    price_at_take="",
                    american_price_at_take="",
                    closing_data_available="false",
                    notes=f"VERIFY({TODAY.isoformat()}): price not on slip; do not invent",
                )
            ],
            now=after,
        )
        self.assertEqual(errors, [], errors)
        self.assertGreaterEqual(debt, 1)

    def test_fail_atd_blank_price_without_verify(self):
        errors, _ = _run(
            [_base_ticket()],
            [
                _base_leg(
                    market="anytime_td",
                    side="Nabers",
                    line_at_take="",
                    price_at_take="",
                    american_price_at_take="",
                    closing_data_available="false",
                    notes="",
                )
            ],
        )
        self.assertTrue(any("missing price" in e for e in errors), errors)

    def test_pass_reconstructed_blank_hard_fields_with_dated_verify(self):
        rec = (
            "RECONSTRUCTED (chat backfill 2026-09-17T21:25, not at-placement). "
            f"VERIFY({TODAY.isoformat()}): leftovers"
        )
        errors, debt = _run(
            [_base_ticket(placed_at="", notes=rec)],
            [
                _base_leg(
                    game_id="",
                    price_at_take="",
                    american_price_at_take="",
                    notes=rec,
                )
            ],
        )
        self.assertEqual(errors, [], errors)
        self.assertGreaterEqual(debt, 2)

    def test_fail_reconstructed_without_dated_verify_still_hard(self):
        errors, _ = _run(
            [
                _base_ticket(
                    placed_at="",
                    notes="RECONSTRUCTED (chat backfill 2026-09-17T21:25, not at-placement)",
                )
            ],
            [_base_leg()],
        )
        self.assertTrue(any("missing placed_at" in e for e in errors), errors)

    def test_fail_verify_other_field_blank_after_kickoff(self):
        # NOW is after kickoff → VERIFY cannot excuse blank book.
        past_kickoff = datetime(2026, 9, 17, 21, 0, 0, tzinfo=TZ)
        errors, _ = _run(
            [
                _base_ticket(
                    book="",
                    notes=f"VERIFY({TODAY.isoformat()}): book TBD",
                )
            ],
            [_base_leg(kickoff_at="2026-09-17T20:15:00-04:00")],
            now=past_kickoff,
        )
        self.assertTrue(
            any("missing book" in e and "cannot excuse" in e for e in errors),
            errors,
        )

    def test_fail_verify_other_field_blank_when_settled(self):
        errors, _ = _run(
            [
                _base_ticket(
                    book="",
                    status="settled",
                    settled="true",
                    notes=f"VERIFY({TODAY.isoformat()}): book TBD",
                )
            ],
            [_base_leg()],
        )
        self.assertTrue(
            any("missing book" in e and "cannot excuse" in e for e in errors),
            errors,
        )

    def test_pass_open_pre_kickoff_with_dated_verify_on_optional_blank(self):
        # All hard/required filled; optional american_price blank with dated VERIFY.
        # Also blank an excusable field? Spec says "dated VERIFY on an optional blank".
        # Use blank market_family (not required) + dated VERIFY — should pass.
        errors, debt = _run(
            [
                _base_ticket(
                    market_family="",
                    notes=f"VERIFY({TODAY.isoformat()}): market_family confirm later",
                )
            ],
            [_base_leg()],
        )
        self.assertEqual(errors, [], errors)
        self.assertGreaterEqual(debt, 1)

    def test_verify_debt_printed_on_success_via_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            tp, lp = _write_csvs(
                Path(tmp),
                [
                    _base_ticket(
                        market_family="",
                        notes=f"VERIFY({TODAY.isoformat()}): optional",
                    )
                ],
                [_base_leg()],
            )
            # Temporarily point defaults by calling main with paths.
            code = validate.main(tp, lp, now=NOW)
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
