#!/usr/bin/env python3
"""stdlib unittest: close_lines refuses writes without a final score."""

from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import close_lines  # noqa: E402


GAMES_HEADER = (
    "game_id,season,week,away_team,away_score,home_team,home_score,"
    "result,total,spread_line,away_spread_odds,home_spread_odds,"
    "total_line,under_odds,over_odds,away_moneyline,home_moneyline"
)

# Live / pre-kickoff: spread present but scores blank — must NOT write closes.
LIVE_GAME = (
    "2026_02_DET_BUF,2026,2,DET,,BUF,,,"
    ",5.5,-115,-105,54.5,-102,-118,195,-238"
)

# Final game with scores + closes.
FINAL_GAME = (
    "2024_01_BAL_KC,2024,1,BAL,20,KC,27,"
    "7,47,3,-118,-102,46,-110,-110,110,-130"
)


def _legs_row(**kwargs: str) -> dict[str, str]:
    base = {
        "leg_id": "leg-1",
        "ticket_id": "tix-1",
        "game_id": "",
        "kickoff_at": "",
        "away_team": "",
        "home_team": "",
        "market": "spread",
        "side": "BUF",
        "line_at_take": "-5.5",
        "price_at_take": "",
        "american_price_at_take": "-110",
        "decimal_price_at_take": "",
        "closing_data_available": "true",
        "closing_line": "",
        "closing_price_american": "",
        "closing_price_decimal": "",
        "clv_no_vig": "",
        "result": "pending",
        "notes": "",
    }
    base.update(kwargs)
    return base


class TestRefuseWithoutFinal(unittest.TestCase):
    def test_live_game_no_closing_write(self) -> None:
        games_text = GAMES_HEADER + "\n" + LIVE_GAME + "\n"
        games = close_lines.load_games_from_text(games_text)
        leg = _legs_row(
            game_id="2026_02_DET_BUF",
            away_team="DET",
            home_team="BUF",
            side="BUF",
            line_at_take="-5.5",
            market="spread",
        )
        self.assertFalse(close_lines.has_final_score(games[0]))
        updates, reason, did = close_lines.process_leg(
            leg, close_lines.index_games(games)
        )
        self.assertFalse(did)
        self.assertEqual(updates, {})
        self.assertIn("no final score", reason)
        self.assertIn("refuse", reason.lower())

    def test_final_game_writes_close(self) -> None:
        games_text = GAMES_HEADER + "\n" + FINAL_GAME + "\n"
        games = close_lines.load_games_from_text(games_text)
        leg = _legs_row(
            game_id="2024_01_BAL_KC",
            away_team="BAL",
            home_team="KC",
            side="KC",
            line_at_take="-3",
            market="spread",
            american_price_at_take="-110",
        )
        updates, reason, did = close_lines.process_leg(
            leg, close_lines.index_games(games)
        )
        self.assertTrue(did)
        # spread_line=3 > 0 home favored → home line = -3
        self.assertEqual(updates["closing_line"], "-3")
        self.assertEqual(updates["closing_price_american"], "-102")
        self.assertEqual(updates["result"], "win")  # KC won by 7, -3 covers
        self.assertTrue(updates["clv_no_vig"])  # both close prices present
        self.assertIn("updated", reason)

    def test_apply_refresh_does_not_corrupt_live(self) -> None:
        games_text = GAMES_HEADER + "\n" + LIVE_GAME + "\n"
        games = close_lines.load_games_from_text(games_text)
        legs = [
            _legs_row(
                game_id="2026_02_DET_BUF",
                side="BUF",
                line_at_take="-5.5",
                closing_line="",
                result="pending",
            )
        ]
        out, _log, updated, skipped = close_lines.apply_refresh(legs, games)
        self.assertEqual(updated, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(out[0]["closing_line"], "")
        self.assertEqual(out[0]["result"], "pending")

    def test_atd_forced_unauditable(self) -> None:
        games = close_lines.load_games_from_text(GAMES_HEADER + "\n" + FINAL_GAME + "\n")
        leg = _legs_row(market="anytime_td", side="Henry", game_id="2024_01_BAL_KC")
        updates, _reason, did = close_lines.process_leg(
            leg, close_lines.index_games(games)
        )
        self.assertTrue(did)
        self.assertEqual(updates["closing_data_available"], "false")
        self.assertEqual(updates["closing_line"], "")
        self.assertEqual(updates["clv_no_vig"], "")


class TestSpreadConvention(unittest.TestCase):
    def test_home_away_lines(self) -> None:
        self.assertEqual(close_lines.closing_spread_line(5.5, "home"), -5.5)
        self.assertEqual(close_lines.closing_spread_line(5.5, "away"), 5.5)
        self.assertEqual(close_lines.closing_spread_line(-3.0, "home"), 3.0)
        self.assertEqual(close_lines.closing_spread_line(-3.0, "away"), -3.0)


if __name__ == "__main__":
    unittest.main()
