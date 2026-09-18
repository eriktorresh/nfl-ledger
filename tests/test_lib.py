#!/usr/bin/env python3
"""stdlib unittest for lib.py odds math (de-vig / CLV)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lib  # noqa: E402


class TestAmericanImplied(unittest.TestCase):
    def test_negative(self) -> None:
        # -110 → 110/210
        self.assertAlmostEqual(lib.american_to_implied(-110), 110 / 210, places=9)

    def test_positive(self) -> None:
        # +100 → 100/200 = 0.5
        self.assertAlmostEqual(lib.american_to_implied(100), 0.5, places=9)
        self.assertAlmostEqual(lib.american_to_implied("+150"), 100 / 250, places=9)

    def test_decimal(self) -> None:
        self.assertAlmostEqual(lib.american_to_decimal(-110), 1 + 100 / 110, places=9)
        self.assertAlmostEqual(lib.american_to_decimal(150), 2.5, places=9)


class TestDevig(unittest.TestCase):
    def test_two_way_symmetric(self) -> None:
        a = lib.american_to_implied(-110)
        b = lib.american_to_implied(-110)
        fa, fb = lib.devig_two_way(a, b)
        self.assertAlmostEqual(fa, 0.5, places=9)
        self.assertAlmostEqual(fb, 0.5, places=9)
        self.assertAlmostEqual(fa + fb, 1.0, places=9)

    def test_two_way_asymmetric(self) -> None:
        a = lib.american_to_implied(-150)
        b = lib.american_to_implied(130)
        fa, fb = lib.devig_two_way(a, b)
        self.assertAlmostEqual(fa + fb, 1.0, places=9)
        self.assertGreater(fa, fb)


class TestClv(unittest.TestCase):
    def test_positive_clv_beat_close(self) -> None:
        # Took +100 (implied 0.5). Close -110/-110 → fair 0.5. CLV=0.
        self.assertAlmostEqual(lib.clv_no_vig(100, -110, -110), 0.0, places=9)

        # Took +120 (offered ~0.4545). Close still -110/-110 fair 0.5.
        # CLV = 0.5 - 100/220 > 0 → beat the close.
        clv = lib.clv_no_vig(120, -110, -110)
        self.assertIsNotNone(clv)
        assert clv is not None
        self.assertGreater(clv, 0)

    def test_negative_clv_worse_than_close(self) -> None:
        # Took -130 (offered high). Close -110/-110 fair 0.5.
        clv = lib.clv_no_vig(-130, -110, -110)
        self.assertIsNotNone(clv)
        assert clv is not None
        self.assertLess(clv, 0)

    def test_missing_other_returns_none(self) -> None:
        self.assertIsNone(lib.clv_no_vig(-110, -110, None))
        self.assertIsNone(lib.clv_no_vig(-110, -110, ""))


if __name__ == "__main__":
    unittest.main()
