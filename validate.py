#!/usr/bin/env python3
"""Validate nfl-ledger CSVs against LEDGER PROTOCOL v0."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TICKETS = ROOT / "data" / "tickets.csv"
LEGS = ROOT / "data" / "legs.csv"

BOOK = {"DK", "HR", "OTHER"}
LANE = {"TNF", "S5", "ATD", "SCREEN", "SGP", "OTHER"}
MARKET_FAMILY = {"SPREAD_TOTAL", "SGP", "ATD", "PARLAY", "OTHER"}
EDGE = {"PLAY", "ENTERTAINMENT", "LOTTERY", "PASS", "UNGRADED", "HOLD", "OTHER"}
STAKE_VS = {"agree", "override"}
STATUS = {"open", "settled", "void", "cashout"}
MARKET = {"spread", "total", "ml", "anytime_td", "first_td", "team_total", "other"}
RESULT = {"pending", "win", "loss", "push", "void", ""}

TICKET_REQUIRED = [
    "ticket_id",
    "placed_at",
    "book",
    "lane",
    "stake_usd",
    "edge_grade_at_placement",
    "stake_vs_grade",
    "status",
]
LEG_REQUIRED = [
    "leg_id",
    "ticket_id",
    "market",
    "side",
    "closing_data_available",
]


def _boolish(v: str) -> str:
    return (v or "").strip().lower()


def _has_verify(notes: str) -> bool:
    return "VERIFY" in (notes or "").upper()


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"missing {path}")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    errors: list[str] = []
    tickets = load_csv(TICKETS)
    legs = load_csv(LEGS)
    ticket_ids = {t.get("ticket_id", "").strip() for t in tickets if t.get("ticket_id")}

    for i, t in enumerate(tickets, start=2):
        tid = (t.get("ticket_id") or "").strip()
        notes = t.get("notes") or ""
        for col in TICKET_REQUIRED:
            val = (t.get(col) or "").strip()
            if not val and not _has_verify(notes):
                errors.append(f"tickets.csv:{i} missing {col} without VERIFY note")
        book = (t.get("book") or "").strip()
        if book and book not in BOOK:
            errors.append(f"tickets.csv:{i} bad book={book!r}")
        lane = (t.get("lane") or "").strip()
        if lane and lane not in LANE:
            errors.append(f"tickets.csv:{i} bad lane={lane!r}")
        mf = (t.get("market_family") or "").strip()
        if mf and mf not in MARKET_FAMILY:
            errors.append(f"tickets.csv:{i} bad market_family={mf!r}")
        eg = (t.get("edge_grade_at_placement") or "").strip()
        if eg and eg not in EDGE:
            errors.append(f"tickets.csv:{i} bad edge_grade_at_placement={eg!r}")
        svg = (t.get("stake_vs_grade") or "").strip()
        if svg and svg not in STAKE_VS:
            errors.append(f"tickets.csv:{i} bad stake_vs_grade={svg!r}")
        st = (t.get("status") or "").strip()
        if st and st not in STATUS:
            errors.append(f"tickets.csv:{i} bad status={st!r}")
        settled = _boolish(t.get("settled") or "")
        stake = (t.get("stake_usd") or "").strip()
        if settled == "true" and stake:
            try:
                if float(stake) > 0 and not svg:
                    errors.append(
                        f"tickets.csv:{i} stake_vs_grade missing when settled stake>0"
                    )
            except ValueError:
                errors.append(f"tickets.csv:{i} stake_usd not decimal: {stake!r}")

    for i, leg in enumerate(legs, start=2):
        notes = leg.get("notes") or ""
        for col in LEG_REQUIRED:
            val = (leg.get(col) or "").strip()
            if not val and not _has_verify(notes):
                errors.append(f"legs.csv:{i} missing {col} without VERIFY note")
        tid = (leg.get("ticket_id") or "").strip()
        if tid and tid not in ticket_ids:
            errors.append(f"legs.csv:{i} orphan ticket_id={tid!r}")
        mkt = (leg.get("market") or "").strip()
        if mkt and mkt not in MARKET:
            errors.append(f"legs.csv:{i} bad market={mkt!r}")
        res = (leg.get("result") or "").strip()
        if res not in RESULT:
            errors.append(f"legs.csv:{i} bad result={res!r}")
        cda = _boolish(leg.get("closing_data_available") or "")
        if mkt in {"anytime_td", "first_td"}:
            if cda not in {"false", ""}:
                errors.append(
                    f"legs.csv:{i} anytime_td/first_td must have closing_data_available=false"
                )
            for col in (
                "closing_line",
                "closing_price_american",
                "closing_price_decimal",
                "clv_no_vig",
            ):
                if (leg.get(col) or "").strip():
                    errors.append(
                        f"legs.csv:{i} {col} must stay blank for anytime_td/first_td"
                    )

    if errors:
        print("validate.py FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(
        f"validate.py OK — {len(tickets)} tickets, {len(legs)} legs (header-only OK)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
