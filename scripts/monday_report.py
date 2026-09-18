#!/usr/bin/env python3
"""Monday scorecard / completed-week report from ledger CSVs.

Usage:
  python scripts/monday_report.py --season 2026 --week 2
  python scripts/monday_report.py          # derive season/week from game_ids

When --season/--week are omitted, unique (season, week) pairs are derived from
leg game_ids (SEASON_WW_AWAY_HOME). Exactly one pair → use it; zero or many →
error (pass flags). Legs without parseable game_id are excluded from the week
filter (shown in coverage notes).

Unauditable stake rule: if a ticket has ANY anytime_td/first_td leg in-scope,
the FULL ticket stake_usd counts toward the unauditable-lane dollar total
(not pro-rata).

Outcome ≠ evidence of grade quality.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lib  # noqa: E402

TICKETS = ROOT / "data" / "tickets.csv"
LEGS = ROOT / "data" / "legs.csv"
SHADOW = ROOT / "data" / "shadow.csv"
SHADOW_LEGS = ROOT / "data" / "shadow_legs.csv"
REPORTS = ROOT / "reports"

UNAEDITABLE = {"anytime_td", "first_td"}

# Hard-coded paper stake for shadow (no-go) tickets — never another unit size.
PAPER_STAKE_USD = 10


def parse_game_id(game_id: str) -> Optional[tuple[int, int, str, str]]:
    parts = (game_id or "").strip().split("_")
    if len(parts) != 4:
        return None
    try:
        return int(parts[0]), int(parts[1]), parts[2], parts[3]
    except ValueError:
        return None


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _float(v: str) -> Optional[float]:
    s = (v or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def paper_stake(row: dict[str, str]) -> float:
    """Shadow paper stake — hard-coded default $10 when blank."""
    v = _float(row.get("paper_stake_usd") or "")
    if v is None:
        return float(PAPER_STAKE_USD)
    return v


def _mean(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return statistics.mean(vals)


def _fmt(v: Optional[float], digits: int = 4) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}"


def derive_season_week(legs: list[dict[str, str]]) -> tuple[int, int]:
    pairs: set[tuple[int, int]] = set()
    for leg in legs:
        parsed = parse_game_id(leg.get("game_id") or "")
        if parsed:
            pairs.add((parsed[0], parsed[1]))
    if len(pairs) == 1:
        return next(iter(pairs))
    if not pairs:
        raise SystemExit(
            "No parseable game_ids in legs.csv — pass --season and --week"
        )
    shown = ", ".join(f"{s}_W{w:02d}" for s, w in sorted(pairs))
    raise SystemExit(
        f"Multiple season/week pairs in legs ({shown}); pass --season and --week"
    )


def leg_in_week(leg: dict[str, str], season: int, week: int) -> bool:
    parsed = parse_game_id(leg.get("game_id") or "")
    if not parsed:
        return False
    return parsed[0] == season and parsed[1] == week


def is_auditable(leg: dict[str, str]) -> bool:
    mkt = (leg.get("market") or "").strip()
    if mkt in UNAEDITABLE:
        return False
    cda = (leg.get("closing_data_available") or "").strip().lower()
    if cda != "true":
        return False
    # closing filled: need closing_line OR (ml with close price); require clv or line
    has_close = bool((leg.get("closing_line") or "").strip()) or bool(
        (leg.get("closing_price_american") or "").strip()
    )
    return has_close


def is_permanently_unauditable(leg: dict[str, str]) -> bool:
    return (leg.get("market") or "").strip() in UNAEDITABLE


def parlay_counterfactual(
    ticket: dict[str, str], ticket_legs: list[dict[str, str]]
) -> str:
    """Simple stub: product of fair closes vs sum of singles EV.

    Requires each leg to have clv_no_vig + american_price_at_take + both-side
    close prices already baked into clv. Uses offered decimal from
    american_price_at_take and fair ≈ offered_implied + clv_no_vig.

    If data insufficient → N/A with reason.
    """
    family = (ticket.get("market_family") or "").strip().upper()
    lane = (ticket.get("lane") or "").strip().upper()
    if family not in {"PARLAY", "SGP"} and lane not in {"S5", "SGP"}:
        if len(ticket_legs) < 2:
            return "N/A (not a multi-leg ticket)"
    if len(ticket_legs) < 2:
        return "N/A (need ≥2 legs)"

    fairs: list[float] = []
    singles_ev: list[float] = []
    for leg in ticket_legs:
        amer = (leg.get("american_price_at_take") or "").strip()
        clv_s = (leg.get("clv_no_vig") or "").strip()
        if not amer or not clv_s:
            return (
                "N/A (need american_price_at_take + clv_no_vig on every leg; "
                "closes may be incomplete)"
            )
        try:
            offered_imp = lib.american_to_implied(amer)
            clv = float(clv_s)
            fair = offered_imp + clv  # since CLV = fair - offered
            dec = lib.american_to_decimal(amer)
        except (ValueError, TypeError):
            return "N/A (could not parse prices/CLV for counterfactual)"
        if fair <= 0 or fair >= 1:
            return "N/A (fair probability out of range)"
        fairs.append(fair)
        # Singles EV per $1 stake at offered price vs fair: fair*dec - 1
        singles_ev.append(fair * dec - 1.0)

    fair_ticket = math.prod(fairs)
    # Parlay multiple from ticket american/decimal if present
    mult = _float(ticket.get("decimal_price") or "")
    if mult is None:
        amer_t = (ticket.get("american_price") or "").strip()
        if amer_t:
            try:
                mult = lib.american_to_decimal(amer_t)
            except (ValueError, TypeError):
                mult = None
    if mult is None:
        # Infer from payout/stake if both present
        stake = _float(ticket.get("stake_usd") or "")
        payout = _float(ticket.get("payout_usd") or "")
        if stake and payout and stake > 0:
            mult = payout / stake
    if mult is None:
        return "N/A (no ticket decimal/american/payout to price the parlay)"

    parlay_ev = fair_ticket * mult - 1.0
    singles_sum = sum(singles_ev)
    return (
        f"stub: fair_ticket={fair_ticket:.4f} × mult={mult:.3f} → "
        f"parlay_EV/stake={parlay_ev:.4f}; "
        f"sum_singles_EV/stake={singles_sum:.4f} "
        f"(Δ parlay−singles={parlay_ev - singles_sum:.4f}). "
        "Stub assumes independence; not a vig-free book parlay price."
    )


def build_report(
    tickets: list[dict[str, str]],
    legs: list[dict[str, str]],
    season: int,
    week: int,
    *,
    shadow: Optional[list[dict[str, str]]] = None,
    shadow_legs: Optional[list[dict[str, str]]] = None,
) -> str:
    week_legs = [L for L in legs if leg_in_week(L, season, week)]
    week_ticket_ids = {L.get("ticket_id") for L in week_legs}
    # Also include tickets that might only be linked — prefer legs filter
    week_tickets = [T for T in tickets if T.get("ticket_id") in week_ticket_ids]

    legs_by_ticket: dict[str, list[dict[str, str]]] = defaultdict(list)
    for L in week_legs:
        legs_by_ticket[L.get("ticket_id") or ""].append(L)

    total_legs = len(week_legs)
    auditable = [L for L in week_legs if is_auditable(L)]
    unaud = [L for L in week_legs if is_permanently_unauditable(L)]
    auditable_n = len(auditable)
    unaud_n = len(unaud)

    # Full ticket stake if ANY unauditable leg
    unaud_ticket_ids = {
        L.get("ticket_id") for L in unaud if L.get("ticket_id")
    }
    unaud_stake = 0.0
    for T in week_tickets:
        if T.get("ticket_id") in unaud_ticket_ids:
            s = _float(T.get("stake_usd") or "")
            if s is not None:
                unaud_stake += s

    lines: list[str] = []
    lines.append(f"# Monday report — {season} week {week:02d}")
    lines.append("")
    lines.append("Outcome ≠ evidence of grade quality.")
    lines.append("")

    # Coverage
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Legs in week (via game_id): **{total_legs}**")
    lines.append(
        f"- Auditable (closing_data_available=true and closing filled): **{auditable_n}**"
    )
    lines.append(
        f"- Permanently unauditable (anytime_td/first_td): **{unaud_n}**"
    )
    lines.append(
        f"- Dollar stake in unauditable lane: **${unaud_stake:.2f}** "
        "(rule: sum **full** ticket `stake_usd` when the ticket has any "
        "anytime_td/first_td leg in this week — not pro-rata)"
    )
    no_gid = sum(1 for L in legs if not parse_game_id(L.get("game_id") or ""))
    if no_gid:
        lines.append(
            f"- Note: {no_gid} leg(s) repo-wide lack parseable game_id "
            "(excluded from week filter)"
        )
    lines.append("")

    # CLV by lane
    lines.append("## CLV by lane")
    lines.append("")
    lines.append(
        "Mean `clv_no_vig` on auditable legs. "
        "Sign: positive = beat the close (good take)."
    )
    lines.append("")
    by_lane: dict[str, list[float]] = defaultdict(list)
    ticket_lane = {
        T.get("ticket_id"): (T.get("lane") or "OTHER").strip() or "OTHER"
        for T in tickets
    }
    for L in auditable:
        clv = _float(L.get("clv_no_vig") or "")
        if clv is None:
            continue
        lane = ticket_lane.get(L.get("ticket_id"), "OTHER")
        by_lane[lane].append(clv)
    if not by_lane:
        lines.append("_No auditable CLV values yet._")
    else:
        lines.append("| Lane | n | mean CLV |")
        lines.append("| --- | ---: | ---: |")
        for lane in sorted(by_lane):
            vals = by_lane[lane]
            lines.append(
                f"| {lane} | {len(vals)} | {_fmt(_mean(vals))} |"
            )
    lines.append("")

    # CLV by edge_grade
    lines.append("## CLV by edge_grade_at_placement")
    lines.append("")
    by_grade: dict[str, list[float]] = defaultdict(list)
    ticket_grade = {
        T.get("ticket_id"): (T.get("edge_grade_at_placement") or "OTHER").strip()
        or "OTHER"
        for T in tickets
    }
    for L in auditable:
        clv = _float(L.get("clv_no_vig") or "")
        if clv is None:
            continue
        g = ticket_grade.get(L.get("ticket_id"), "OTHER")
        by_grade[g].append(clv)
    if not by_grade:
        lines.append("_No auditable CLV values yet._")
    else:
        lines.append("| Grade | n | mean CLV |")
        lines.append("| --- | ---: | ---: |")
        for g in sorted(by_grade):
            vals = by_grade[g]
            lines.append(f"| {g} | {len(vals)} | {_fmt(_mean(vals))} |")
    lines.append("")

    # PLAY vs PASS
    lines.append("## PLAY vs PASS CLV separation")
    lines.append("")
    play_vals = by_grade.get("PLAY", [])
    pass_vals = by_grade.get("PASS", [])
    play_m = _mean(play_vals)
    pass_m = _mean(pass_vals)
    lines.append(f"- PLAY: n={len(play_vals)} mean={_fmt(play_m)}")
    lines.append(f"- PASS: n={len(pass_vals)} mean={_fmt(pass_m)}")
    if play_m is not None and pass_m is not None:
        lines.append(f"- Separation (PLAY − PASS): {_fmt(play_m - pass_m)}")
    else:
        lines.append("- Separation: N/A")
    lines.append(
        "- Note: **meaningless below ~25–30 legs per bucket** — treat small-n "
        "gaps as noise."
    )
    lines.append("")

    # Overrides
    lines.append("## Overrides")
    lines.append("")
    n_tickets = len(week_tickets)
    n_override = sum(
        1
        for T in week_tickets
        if (T.get("stake_vs_grade") or "").strip() == "override"
    )
    rate = (n_override / n_tickets) if n_tickets else None
    lines.append(f"- Tickets in week: **{n_tickets}**")
    lines.append(f"- Overrides (`stake_vs_grade=override`): **{n_override}**")
    lines.append(
        f"- Override rate: **{_fmt(rate, 3) if rate is not None else 'N/A'}**"
    )
    lines.append("")

    # Parlay counterfactual
    lines.append("## Parlay vs same-legs-as-singles counterfactual")
    lines.append("")
    multi = [
        T
        for T in week_tickets
        if len(legs_by_ticket.get(T.get("ticket_id") or "", [])) >= 2
    ]
    if not multi:
        lines.append("N/A — no multi-leg tickets in this week.")
    else:
        for T in multi:
            tid = T.get("ticket_id") or ""
            cf = parlay_counterfactual(T, legs_by_ticket.get(tid, []))
            lines.append(f"- `{tid[:8]}…` ({T.get('lane')}/{T.get('market_family')}): {cf}")
    lines.append("")

    # Budget adherence
    lines.append("## Budget adherence by lane")
    lines.append("")
    lines.append(
        "N/A — `config.json` not in repo yet (lane budgets land in a follow-up PR)."
    )
    lines.append("")

    # Taken vs shadow (no-go book)
    lines.append("## Taken vs shadow")
    lines.append("")
    lines.append(
        "Compare **taken** portfolio vs **graded but not taken** (shadow) tickets. "
        f"Shadow paper stake is hard-coded at **${PAPER_STAKE_USD:.0f}** per ticket."
    )
    lines.append("")
    lines.append(
        "_No backfill of old PASSes; shadow starts empty until Edge logs "
        "decisions at decision time._"
    )
    lines.append("")

    shadow = shadow or []
    shadow_legs = shadow_legs or []

    # Taken summary (week-scoped tickets)
    taken_count = len(week_tickets)
    taken_stake = 0.0
    taken_settled_returned = 0.0
    taken_open_stake = 0.0
    for T in week_tickets:
        s = _float(T.get("stake_usd") or "") or 0.0
        taken_stake += s
        status = (T.get("status") or "").strip()
        settled = (T.get("settled") or "").strip().lower()
        if status == "open":
            taken_open_stake += s
        if settled == "true" or status == "settled":
            ret = _float(T.get("returned_usd") or "")
            if ret is not None:
                taken_settled_returned += ret

    lines.append("### Taken")
    lines.append("")
    lines.append(f"- Ticket count: **{taken_count}**")
    lines.append(f"- Stake: **${taken_stake:.2f}**")
    lines.append(f"- Settled returned: **${taken_settled_returned:.2f}**")
    lines.append(f"- Open stake: **${taken_open_stake:.2f}**")
    lines.append("")

    # Shadow week scope via shadow_legs game_id
    week_shadow_legs = [L for L in shadow_legs if leg_in_week(L, season, week)]
    week_shadow_ids = {L.get("shadow_id") for L in week_shadow_legs if L.get("shadow_id")}
    # Also include shadow rows whose decided_at week we cannot infer from legs —
    # prefer legs filter; if no shadow_legs in week, still show empty counts.
    week_shadow = [S for S in shadow if S.get("shadow_id") in week_shadow_ids]
    # If shadow has rows but no legs yet, do not invent week membership.
    if not week_shadow_ids and not week_shadow_legs:
        week_shadow = []

    by_grade_shadow: dict[str, int] = defaultdict(int)
    shadow_paper_stake = 0.0
    shadow_settled_pnl = 0.0
    shadow_settled_n = 0
    play_skipped = 0
    pass_logged = 0
    for S in week_shadow:
        g = (S.get("edge_grade") or "OTHER").strip() or "OTHER"
        by_grade_shadow[g] += 1
        pstake = paper_stake(S)
        shadow_paper_stake += pstake
        reason = (S.get("reason_not_taken") or "").strip()
        if reason == "skip_play":
            play_skipped += 1
        if reason == "pass_edge" or g == "PASS":
            pass_logged += 1
        status = (S.get("status") or "").strip()
        settled = (S.get("settled") or "").strip().lower()
        if settled == "true" or status == "settled":
            shadow_settled_n += 1
            ret = _float(S.get("returned_usd") or "")
            if ret is not None:
                shadow_settled_pnl += ret - pstake
            else:
                # No return logged yet — P&L unknown for this row
                pass

    lines.append("### Shadow (no-go)")
    lines.append("")
    lines.append(f"- Shadow tickets in week: **{len(week_shadow)}**")
    if by_grade_shadow:
        lines.append("- Count by `edge_grade`:")
        for g in sorted(by_grade_shadow):
            lines.append(f"  - {g}: **{by_grade_shadow[g]}**")
    else:
        lines.append("- Count by `edge_grade`: _(none)_")
    lines.append(
        f"- Paper stake (sum, ${PAPER_STAKE_USD:.0f}/ticket default): "
        f"**${shadow_paper_stake:.2f}**"
    )
    if shadow_settled_n:
        lines.append(
            f"- Settled paper P&L (returned − paper stake): "
            f"**${shadow_settled_pnl:.2f}** ({shadow_settled_n} settled)"
        )
    else:
        lines.append("- Settled paper P&L: **N/A** (none settled)")
    lines.append(f"- PLAY skipped (`reason_not_taken=skip_play`): **{play_skipped}**")
    lines.append(
        f"- PASS logged (`reason_not_taken=pass_edge` or `edge_grade=PASS`): "
        f"**{pass_logged}**"
    )
    lines.append("")

    # CLV: auditable taken legs vs auditable shadow legs
    taken_clvs = [
        c
        for L in auditable
        if (c := _float(L.get("clv_no_vig") or "")) is not None
    ]
    shadow_auditable = [L for L in week_shadow_legs if is_auditable(L)]
    shadow_clvs = [
        c
        for L in shadow_auditable
        if (c := _float(L.get("clv_no_vig") or "")) is not None
    ]
    lines.append("### CLV (auditable legs)")
    lines.append("")
    lines.append(
        f"- Taken mean CLV: n={len(taken_clvs)} mean={_fmt(_mean(taken_clvs))}"
    )
    lines.append(
        f"- Shadow mean CLV: n={len(shadow_clvs)} mean={_fmt(_mean(shadow_clvs))}"
    )
    lines.append("")

    # Process notes
    lines.append("## Process notes (hand-filled)")
    lines.append("")
    lines.append("_<!-- blank: fill manually after reading the numbers -->_")
    lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season", type=int, default=None, help="NFL season year")
    p.add_argument("--week", type=int, default=None, help="NFL week number")
    p.add_argument(
        "--write",
        action="store_true",
        help="Also write reports/YYYY_WW.md",
    )
    p.add_argument("--tickets", default=str(TICKETS))
    p.add_argument("--legs", default=str(LEGS))
    p.add_argument("--shadow", default=str(SHADOW))
    p.add_argument("--shadow-legs", default=str(SHADOW_LEGS))
    args = p.parse_args(argv)

    tickets = load_csv(Path(args.tickets))
    legs = load_csv(Path(args.legs))
    shadow_path = Path(args.shadow)
    shadow_legs_path = Path(args.shadow_legs)
    shadow = load_csv(shadow_path) if shadow_path.exists() else []
    shadow_legs = (
        load_csv(shadow_legs_path) if shadow_legs_path.exists() else []
    )

    if args.season is None or args.week is None:
        if args.season is not None or args.week is not None:
            print("Pass both --season and --week, or neither.", file=sys.stderr)
            return 2
        # Prefer taken legs; fall back to shadow_legs if taken empty of game_ids
        try:
            season, week = derive_season_week(legs)
        except SystemExit:
            season, week = derive_season_week(shadow_legs)
    else:
        season, week = args.season, args.week

    md = build_report(
        tickets,
        legs,
        season,
        week,
        shadow=shadow,
        shadow_legs=shadow_legs,
    )
    sys.stdout.write(md)

    if args.write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        out = REPORTS / f"{season}_{week:02d}.md"
        out.write_text(md, encoding="utf-8")
        print(f"\n(wrote {out})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
