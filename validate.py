#!/usr/bin/env python3
"""Validate nfl-ledger CSVs against LEDGER PROTOCOL v0."""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TICKETS = ROOT / "data" / "tickets.csv"
LEGS = ROOT / "data" / "legs.csv"
SHADOW = ROOT / "data" / "shadow.csv"
SHADOW_LEGS = ROOT / "data" / "shadow_legs.csv"
TZ = ZoneInfo("America/New_York")

# Default paper stake for shadow (no-go) tickets — hard-coded unit size.
PAPER_STAKE_USD = 10

BOOK = {"DK", "HR", "OTHER"}
LANE = {"TNF", "S5", "ATD", "SCREEN", "SGP", "OTHER"}
MARKET_FAMILY = {"SPREAD_TOTAL", "SGP", "ATD", "PARLAY", "OTHER"}
EDGE = {"PLAY", "ENTERTAINMENT", "LOTTERY", "PASS", "UNGRADED", "HOLD", "OTHER"}
STAKE_VS = {"agree", "override"}
STATUS = {"open", "settled", "void", "cashout"}
STATUS_NO_VERIFY_EXCUSE = {"settled", "void", "cashout"}
SHADOW_STATUS = {"open", "settled", "void", "expired"}
SHADOW_STATUS_NO_VERIFY_EXCUSE = {"settled", "void", "expired"}
REASON_NOT_TAKEN = {
    "pass_edge",
    "skip_entertainment",
    "skip_play",
    "budget",
    "user",
    "other",
}
MARKET = {"spread", "total", "ml", "anytime_td", "first_td", "team_total", "other"}
RESULT = {"pending", "win", "loss", "push", "void", ""}

# Hard required on tickets — VERIFY never excuses these.
TICKET_HARD_REQUIRED = ["placed_at"]
# Full ticket required set (hard + excusable).
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
TICKET_EXCUSABLE = [c for c in TICKET_REQUIRED if c not in TICKET_HARD_REQUIRED]

# Hard required on legs — VERIFY never excuses these.
# price: at least one of price_at_take OR american_price_at_take (checked separately).
LEG_HARD_REQUIRED = ["game_id"]
LEG_REQUIRED = [
    "leg_id",
    "ticket_id",
    "market",
    "side",
    "closing_data_available",
]
LEG_EXCUSABLE = list(LEG_REQUIRED)

# Shadow is a decision log — decided_at always required (VERIFY never excuses).
SHADOW_HARD_REQUIRED = ["decided_at"]
SHADOW_REQUIRED = [
    "shadow_id",
    "decided_at",
    "book",
    "lane",
    "edge_grade",
    "paper_stake_usd",
    "reason_not_taken",
    "status",
]
SHADOW_EXCUSABLE = [c for c in SHADOW_REQUIRED if c not in SHADOW_HARD_REQUIRED]

SHADOW_LEG_HARD_REQUIRED = ["game_id"]
SHADOW_LEG_REQUIRED = [
    "leg_id",
    "shadow_id",
    "market",
    "side",
    "closing_data_available",
]
SHADOW_LEG_EXCUSABLE = list(SHADOW_LEG_REQUIRED)

VERIFY_RE = re.compile(r"VERIFY\((\d{4}-\d{2}-\d{2})\):")


def _boolish(v: str) -> str:
    return (v or "").strip().lower()


def _has_verify_token(notes: str) -> bool:
    return "VERIFY" in (notes or "").upper()


def _verify_match(notes: str) -> re.Match[str] | None:
    return VERIFY_RE.search(notes or "")


def _is_reconstructed(notes: str) -> bool:
    return "RECONSTRUCTED" in (notes or "").upper()


def _reconstructed_hard_ok(notes: str, has_dated: bool) -> bool:
    """Chat backfill rows may leave hard fields blank; do not invent them."""
    return has_dated and _is_reconstructed(notes)


def _parse_kickoff(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"missing {path}")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _ticket_verify_excuse_ok(
    status: str, ticket_legs: list[dict[str, str]], now: datetime
) -> bool:
    """VERIFY may excuse other fields only while status=open and kickoff not passed."""
    if status in STATUS_NO_VERIFY_EXCUSE:
        return False
    if status != "open":
        return False
    kickoffs = [_parse_kickoff(leg.get("kickoff_at") or "") for leg in ticket_legs]
    present = [k for k in kickoffs if k is not None]
    if not present:
        # All kickoff_at blank → still allow VERIFY excuse when status=open.
        return True
    return min(present) >= now


def _shadow_verify_excuse_ok(
    status: str, shadow_legs: list[dict[str, str]], now: datetime
) -> bool:
    """VERIFY may excuse other shadow fields only while status=open and kickoff not passed."""
    if status in SHADOW_STATUS_NO_VERIFY_EXCUSE:
        return False
    if status != "open":
        return False
    kickoffs = [_parse_kickoff(leg.get("kickoff_at") or "") for leg in shadow_legs]
    present = [k for k in kickoffs if k is not None]
    if not present:
        return True
    return min(present) >= now


def _check_verify_note(
    label: str, notes: str, today: date, errors: list[str]
) -> bool:
    """
    If notes mention VERIFY, require VERIFY(YYYY-MM-DD): within 7 days.
    Returns True if a dated VERIFY note is present (counts toward VERIFY-debt).
    """
    if not _has_verify_token(notes):
        return False
    m = _verify_match(notes)
    if not m:
        errors.append(
            f"{label} VERIFY note missing/malformed date; "
            f"need VERIFY(YYYY-MM-DD):"
        )
        return False
    try:
        vd = date.fromisoformat(m.group(1))
    except ValueError:
        errors.append(f"{label} VERIFY date not valid YYYY-MM-DD: {m.group(1)!r}")
        return False
    if vd < today - timedelta(days=7):
        errors.append(
            f"{label} VERIFY date {vd.isoformat()} is more than 7 days before today"
        )
        return False
    return True


def _check_atd_closing(label: str, leg: dict[str, str], errors: list[str]) -> None:
    mkt = (leg.get("market") or "").strip()
    cda = _boolish(leg.get("closing_data_available") or "")
    if mkt in {"anytime_td", "first_td"}:
        if cda not in {"false", ""}:
            errors.append(
                f"{label} anytime_td/first_td must have closing_data_available=false"
            )
        for col in (
            "closing_line",
            "closing_price_american",
            "closing_price_decimal",
            "clv_no_vig",
        ):
            if (leg.get(col) or "").strip():
                errors.append(
                    f"{label} {col} must stay blank for anytime_td/first_td"
                )


def validate(
    tickets: list[dict[str, str]],
    legs: list[dict[str, str]],
    *,
    now: datetime | None = None,
    shadow: list[dict[str, str]] | None = None,
    shadow_legs: list[dict[str, str]] | None = None,
) -> tuple[list[str], int]:
    """Return (errors, verify_debt_count).

    shadow / shadow_legs are optional for backward-compatible unit tests;
    when omitted, only tickets/legs are checked.
    """
    errors: list[str] = []
    if now is None:
        now = datetime.now(TZ)
    else:
        if now.tzinfo is None:
            now = now.replace(tzinfo=TZ)
        else:
            now = now.astimezone(TZ)
    today = now.date()

    ticket_ids = {t.get("ticket_id", "").strip() for t in tickets if t.get("ticket_id")}
    legs_by_ticket: dict[str, list[dict[str, str]]] = {}
    for leg in legs:
        tid = (leg.get("ticket_id") or "").strip()
        legs_by_ticket.setdefault(tid, []).append(leg)

    ticket_by_id: dict[str, dict[str, str]] = {}
    for t in tickets:
        tid = (t.get("ticket_id") or "").strip()
        if tid:
            ticket_by_id[tid] = t

    verify_debt = 0

    for i, t in enumerate(tickets, start=2):
        tid = (t.get("ticket_id") or "").strip()
        notes = t.get("notes") or ""
        label = f"tickets.csv:{i}"
        has_dated = _check_verify_note(label, notes, today, errors)
        if has_dated:
            verify_debt += 1

        status = (t.get("status") or "").strip()
        t_legs = legs_by_ticket.get(tid, [])
        excuse_ok = False
        if _has_verify_token(notes) and _verify_match(notes):
            # Only a well-formed dated VERIFY can excuse, and only under timing rules.
            excuse_ok = _ticket_verify_excuse_ok(status, t_legs, now)

        for col in TICKET_HARD_REQUIRED:
            val = (t.get(col) or "").strip()
            if not val and not _reconstructed_hard_ok(notes, has_dated):
                errors.append(f"{label} missing {col} (VERIFY never excuses)")

        for col in TICKET_EXCUSABLE:
            val = (t.get(col) or "").strip()
            if not val and not excuse_ok:
                if _has_verify_token(notes):
                    errors.append(
                        f"{label} missing {col}; VERIFY cannot excuse "
                        f"(status={status!r} or kickoff passed/blank rules)"
                    )
                else:
                    errors.append(f"{label} missing {col} without VERIFY note")

        book = (t.get("book") or "").strip()
        if book and book not in BOOK:
            errors.append(f"{label} bad book={book!r}")
        lane = (t.get("lane") or "").strip()
        if lane and lane not in LANE:
            errors.append(f"{label} bad lane={lane!r}")
        mf = (t.get("market_family") or "").strip()
        if mf and mf not in MARKET_FAMILY:
            errors.append(f"{label} bad market_family={mf!r}")
        eg = (t.get("edge_grade_at_placement") or "").strip()
        if eg and eg not in EDGE:
            errors.append(f"{label} bad edge_grade_at_placement={eg!r}")
        svg = (t.get("stake_vs_grade") or "").strip()
        if svg and svg not in STAKE_VS:
            errors.append(f"{label} bad stake_vs_grade={svg!r}")
        if status and status not in STATUS:
            errors.append(f"{label} bad status={status!r}")
        settled = _boolish(t.get("settled") or "")
        stake = (t.get("stake_usd") or "").strip()
        if settled == "true" and stake:
            try:
                if float(stake) > 0 and not svg:
                    errors.append(
                        f"{label} stake_vs_grade missing when settled stake>0"
                    )
            except ValueError:
                errors.append(f"{label} stake_usd not decimal: {stake!r}")

    for i, leg in enumerate(legs, start=2):
        notes = leg.get("notes") or ""
        label = f"legs.csv:{i}"
        has_dated = _check_verify_note(label, notes, today, errors)
        if has_dated:
            verify_debt += 1

        tid = (leg.get("ticket_id") or "").strip()
        parent = ticket_by_id.get(tid)
        parent_status = (parent.get("status") or "").strip() if parent else ""
        t_legs = legs_by_ticket.get(tid, [])
        excuse_ok = False
        if _has_verify_token(notes) and _verify_match(notes) and parent:
            excuse_ok = _ticket_verify_excuse_ok(parent_status, t_legs, now)

        recon_ok = _reconstructed_hard_ok(notes, has_dated)
        for col in LEG_HARD_REQUIRED:
            val = (leg.get(col) or "").strip()
            if not val and not recon_ok:
                errors.append(f"{label} missing {col} (VERIFY never excuses)")

        price_at = (leg.get("price_at_take") or "").strip()
        amer_at = (leg.get("american_price_at_take") or "").strip()
        if not price_at and not amer_at and not recon_ok:
            errors.append(
                f"{label} missing price "
                f"(need price_at_take or american_price_at_take; VERIFY never excuses)"
            )

        for col in LEG_EXCUSABLE:
            val = (leg.get(col) or "").strip()
            if not val and not excuse_ok:
                if _has_verify_token(notes):
                    errors.append(
                        f"{label} missing {col}; VERIFY cannot excuse "
                        f"(status={parent_status!r} or kickoff passed/blank rules)"
                    )
                else:
                    errors.append(f"{label} missing {col} without VERIFY note")

        if tid and tid not in ticket_ids:
            errors.append(f"{label} orphan ticket_id={tid!r}")
        mkt = (leg.get("market") or "").strip()
        if mkt and mkt not in MARKET:
            errors.append(f"{label} bad market={mkt!r}")
        res = (leg.get("result") or "").strip()
        if res not in RESULT:
            errors.append(f"{label} bad result={res!r}")
        _check_atd_closing(label, leg, errors)

    if shadow is not None and shadow_legs is not None:
        shadow_errors, shadow_debt = _validate_shadow(
            shadow, shadow_legs, now=now, today=today
        )
        errors.extend(shadow_errors)
        verify_debt += shadow_debt

    return errors, verify_debt


def _validate_shadow(
    shadow: list[dict[str, str]],
    shadow_legs: list[dict[str, str]],
    *,
    now: datetime,
    today: date,
) -> tuple[list[str], int]:
    errors: list[str] = []
    verify_debt = 0

    shadow_ids = {
        s.get("shadow_id", "").strip() for s in shadow if s.get("shadow_id")
    }
    legs_by_shadow: dict[str, list[dict[str, str]]] = {}
    for leg in shadow_legs:
        sid = (leg.get("shadow_id") or "").strip()
        legs_by_shadow.setdefault(sid, []).append(leg)

    shadow_by_id: dict[str, dict[str, str]] = {}
    for s in shadow:
        sid = (s.get("shadow_id") or "").strip()
        if sid:
            shadow_by_id[sid] = s

    for i, row in enumerate(shadow, start=2):
        sid = (row.get("shadow_id") or "").strip()
        notes = row.get("notes") or ""
        label = f"shadow.csv:{i}"
        has_dated = _check_verify_note(label, notes, today, errors)
        if has_dated:
            verify_debt += 1

        status = (row.get("status") or "").strip()
        s_legs = legs_by_shadow.get(sid, [])
        excuse_ok = False
        if _has_verify_token(notes) and _verify_match(notes):
            excuse_ok = _shadow_verify_excuse_ok(status, s_legs, now)

        # decided_at is always required — VERIFY never excuses (decision log).
        for col in SHADOW_HARD_REQUIRED:
            val = (row.get(col) or "").strip()
            if not val and not _reconstructed_hard_ok(notes, has_dated):
                errors.append(f"{label} missing {col} (VERIFY never excuses)")

        for col in SHADOW_EXCUSABLE:
            val = (row.get(col) or "").strip()
            if not val and not excuse_ok:
                if _has_verify_token(notes):
                    errors.append(
                        f"{label} missing {col}; VERIFY cannot excuse "
                        f"(status={status!r} or kickoff passed/blank rules)"
                    )
                else:
                    errors.append(f"{label} missing {col} without VERIFY note")

        book = (row.get("book") or "").strip()
        if book and book not in BOOK:
            errors.append(f"{label} bad book={book!r}")
        lane = (row.get("lane") or "").strip()
        if lane and lane not in LANE:
            errors.append(f"{label} bad lane={lane!r}")
        mf = (row.get("market_family") or "").strip()
        if mf and mf not in MARKET_FAMILY:
            errors.append(f"{label} bad market_family={mf!r}")
        eg = (row.get("edge_grade") or "").strip()
        if eg and eg not in EDGE:
            errors.append(f"{label} bad edge_grade={eg!r}")
        reason = (row.get("reason_not_taken") or "").strip()
        if reason and reason not in REASON_NOT_TAKEN:
            errors.append(f"{label} bad reason_not_taken={reason!r}")
        if status and status not in SHADOW_STATUS:
            errors.append(f"{label} bad status={status!r}")

        paper = (row.get("paper_stake_usd") or "").strip()
        if paper:
            try:
                pval = float(paper)
            except ValueError:
                errors.append(f"{label} paper_stake_usd not decimal: {paper!r}")
            else:
                # Hard-coded unit size: new shadow rows use exactly $10.
                if abs(pval - PAPER_STAKE_USD) > 1e-9:
                    errors.append(
                        f"{label} paper_stake_usd must be {PAPER_STAKE_USD} "
                        f"(got {paper!r})"
                    )

    for i, leg in enumerate(shadow_legs, start=2):
        notes = leg.get("notes") or ""
        label = f"shadow_legs.csv:{i}"
        has_dated = _check_verify_note(label, notes, today, errors)
        if has_dated:
            verify_debt += 1

        sid = (leg.get("shadow_id") or "").strip()
        parent = shadow_by_id.get(sid)
        parent_status = (parent.get("status") or "").strip() if parent else ""
        s_legs = legs_by_shadow.get(sid, [])
        excuse_ok = False
        if _has_verify_token(notes) and _verify_match(notes) and parent:
            excuse_ok = _shadow_verify_excuse_ok(parent_status, s_legs, now)

        recon_ok = _reconstructed_hard_ok(notes, has_dated)
        for col in SHADOW_LEG_HARD_REQUIRED:
            val = (leg.get(col) or "").strip()
            if not val and not recon_ok:
                errors.append(f"{label} missing {col} (VERIFY never excuses)")

        price_at = (leg.get("price_at_take") or "").strip()
        amer_at = (leg.get("american_price_at_take") or "").strip()
        if not price_at and not amer_at and not recon_ok:
            errors.append(
                f"{label} missing price "
                f"(need price_at_take or american_price_at_take; VERIFY never excuses)"
            )

        for col in SHADOW_LEG_EXCUSABLE:
            val = (leg.get(col) or "").strip()
            if not val and not excuse_ok:
                if _has_verify_token(notes):
                    errors.append(
                        f"{label} missing {col}; VERIFY cannot excuse "
                        f"(status={parent_status!r} or kickoff passed/blank rules)"
                    )
                else:
                    errors.append(f"{label} missing {col} without VERIFY note")

        if sid and sid not in shadow_ids:
            errors.append(f"{label} orphan shadow_id={sid!r}")
        mkt = (leg.get("market") or "").strip()
        if mkt and mkt not in MARKET:
            errors.append(f"{label} bad market={mkt!r}")
        res = (leg.get("result") or "").strip()
        if res not in RESULT:
            errors.append(f"{label} bad result={res!r}")
        _check_atd_closing(label, leg, errors)

    return errors, verify_debt


def main(
    tickets_path: Path = TICKETS,
    legs_path: Path = LEGS,
    *,
    now: datetime | None = None,
    shadow_path: Path | None = None,
    shadow_legs_path: Path | None = None,
) -> int:
    tickets = load_csv(tickets_path)
    legs = load_csv(legs_path)

    # Default: load shadow files next to data/ when present (repo layout).
    if shadow_path is None:
        shadow_path = tickets_path.parent / "shadow.csv"
    if shadow_legs_path is None:
        shadow_legs_path = tickets_path.parent / "shadow_legs.csv"

    shadow: list[dict[str, str]] | None = None
    shadow_legs: list[dict[str, str]] | None = None
    if shadow_path.exists() and shadow_legs_path.exists():
        shadow = load_csv(shadow_path)
        shadow_legs = load_csv(shadow_legs_path)
    elif shadow_path.exists() or shadow_legs_path.exists():
        missing = shadow_legs_path if shadow_path.exists() else shadow_path
        print(f"validate.py FAILED: missing paired shadow file {missing}")
        return 1

    errors, verify_debt = validate(
        tickets,
        legs,
        now=now,
        shadow=shadow,
        shadow_legs=shadow_legs,
    )
    if errors:
        print("validate.py FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(f"VERIFY-debt: {verify_debt}")
        return 1
    shadow_n = len(shadow) if shadow is not None else 0
    shadow_legs_n = len(shadow_legs) if shadow_legs is not None else 0
    print(
        f"validate.py OK — {len(tickets)} tickets, {len(legs)} legs, "
        f"{shadow_n} shadow, {shadow_legs_n} shadow_legs (header-only OK)"
    )
    print(f"VERIFY-debt: {verify_debt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
