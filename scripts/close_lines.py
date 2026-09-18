#!/usr/bin/env python3
"""Refresh closing lines — Tuesday after week final ONLY.

Usage: python scripts/close_lines.py --refresh

Pulls nflverse nfldata games.csv. Joins legs (and shadow_legs) on game_id
(SEASON_WW_AWAY_HOME). Refuses to write any closing_* values for games
without a final score (blank home_score/away_score). Never writes a live
spread as close. anytime_td / first_td: closing_data_available=false forever;
closing columns stay blank (never estimated). Also refreshes shadow_legs.csv
with the same refuse-without-final and ATD rules.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lib  # noqa: E402

LEGS = ROOT / "data" / "legs.csv"
SHADOW_LEGS = ROOT / "data" / "shadow_legs.csv"
NFLVERSE_GAMES_URL = (
    "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
)

# Columns this script may write (nothing else).
WRITABLE = (
    "closing_data_available",
    "closing_line",
    "closing_price_american",
    "closing_price_decimal",
    "clv_no_vig",
    "result",
)

UNAEDITABLE_MARKETS = {"anytime_td", "first_td"}


def fetch_games_csv(url: str = NFLVERSE_GAMES_URL) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(raw)))


def load_games_from_text(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def index_games(games: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for g in games:
        gid = (g.get("game_id") or "").strip()
        if gid:
            out[gid] = g
    return out


def parse_game_id(game_id: str) -> Optional[tuple[int, int, str, str]]:
    """Parse SEASON_WW_AWAY_HOME → (season, week, away, home)."""
    parts = (game_id or "").strip().split("_")
    if len(parts) != 4:
        return None
    season_s, week_s, away, home = parts
    try:
        season = int(season_s)
        week = int(week_s)
    except ValueError:
        return None
    if not away or not home:
        return None
    return season, week, away, home


def _blank(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def has_final_score(game: dict[str, str]) -> bool:
    """True only when both scores are present (game is final)."""
    if _blank(game.get("home_score")) or _blank(game.get("away_score")):
        return False
    try:
        float(str(game["home_score"]).strip())
        float(str(game["away_score"]).strip())
    except ValueError:
        return False
    return True


def _f(v: Any) -> Optional[float]:
    if _blank(v):
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _american_str(v: Any) -> str:
    if _blank(v):
        return ""
    try:
        n = int(float(str(v).strip()))
    except ValueError:
        return ""
    if n > 0:
        return f"+{n}"
    return str(n)


def _fmt_line(x: float) -> str:
    """Compact line string: -3 not -3.0; keep .5 halves."""
    if float(x) == int(x):
        return str(int(x))
    return str(float(x))


def side_home_away(
    side: str, home: str, away: str
) -> Optional[str]:
    s = (side or "").strip().upper()
    if s == (home or "").strip().upper():
        return "home"
    if s == (away or "").strip().upper():
        return "away"
    return None


def closing_spread_line(spread_line: float, which: str) -> float:
    """User convention: spread_line > 0 ⇒ home favored.

    Home side's own line = -spread_line; away side's = +spread_line.
    """
    if which == "home":
        return -spread_line
    if which == "away":
        return +spread_line
    raise ValueError(f"which must be home|away, got {which!r}")


def grade_spread(
    which: str,
    line_at_take: float,
    home_score: float,
    away_score: float,
) -> str:
    margin = (home_score - away_score) if which == "home" else (away_score - home_score)
    adj = margin + line_at_take
    if abs(adj) < 1e-9:
        return "push"
    return "win" if adj > 0 else "loss"


def grade_total(
    side: str, line_at_take: float, home_score: float, away_score: float
) -> str:
    total = home_score + away_score
    s = (side or "").strip().lower()
    if s == "over":
        if total > line_at_take:
            return "win"
        if total < line_at_take:
            return "loss"
        return "push"
    if s == "under":
        if total < line_at_take:
            return "win"
        if total > line_at_take:
            return "loss"
        return "push"
    return "void"


def grade_ml(
    which: str, home_score: float, away_score: float
) -> str:
    if home_score == away_score:
        return "push"
    home_won = home_score > away_score
    if which == "home":
        return "win" if home_won else "loss"
    return "win" if not home_won else "loss"


def compute_clv(
    taken_american: str,
    close_taken: str,
    close_other: str,
) -> str:
    if _blank(taken_american) or _blank(close_taken) or _blank(close_other):
        return ""
    try:
        val = lib.clv_no_vig(taken_american, close_taken, close_other)
    except (ValueError, TypeError):
        return ""
    if val is None:
        return ""
    return f"{val:.6f}".rstrip("0").rstrip(".")


def process_leg(
    leg: dict[str, str], games_by_id: dict[str, dict[str, str]]
) -> tuple[dict[str, str], str, bool]:
    """Return (updates, reason, updated?).

    updates only contains WRITABLE keys when applying a change.
    """
    market = (leg.get("market") or "").strip()
    leg_id = (leg.get("leg_id") or "").strip() or "?"

    if market in UNAEDITABLE_MARKETS:
        updates = {
            "closing_data_available": "false",
            "closing_line": "",
            "closing_price_american": "",
            "closing_price_decimal": "",
            "clv_no_vig": "",
            # do not invent result for props
        }
        # Only touch result if we would clear closing cols; leave result alone.
        return updates, f"{leg_id}: {market} permanently unauditable", True

    game_id = (leg.get("game_id") or "").strip()
    if not game_id:
        return {}, f"{leg_id}: skip — missing game_id", False

    parsed = parse_game_id(game_id)
    if parsed is None:
        return {}, f"{leg_id}: skip — unparseable game_id={game_id!r}", False

    game = games_by_id.get(game_id)
    if game is None:
        # Fallback: season+week+away+home match (same as game_id usually)
        season, week, away, home = parsed
        for g in games_by_id.values():
            try:
                if (
                    int(g.get("season") or -1) == season
                    and int(g.get("week") or -1) == week
                    and (g.get("away_team") or "").strip() == away
                    and (g.get("home_team") or "").strip() == home
                ):
                    game = g
                    break
            except ValueError:
                continue
    if game is None:
        return {}, f"{leg_id}: skip — game_id {game_id} not in nflverse games.csv", False

    if not has_final_score(game):
        return (
            {},
            f"{leg_id}: skip — no final score for {game_id} "
            "(refuse live/pre-kickoff close)",
            False,
        )

    home = (game.get("home_team") or "").strip()
    away = (game.get("away_team") or "").strip()
    home_score = float(str(game["home_score"]).strip())
    away_score = float(str(game["away_score"]).strip())
    side = (leg.get("side") or "").strip()
    line_at_take = _f(leg.get("line_at_take"))
    taken_amer = (leg.get("american_price_at_take") or "").strip()
    if not taken_amer:
        # price_at_take sometimes holds american; do not invent — only use
        # american_price_at_take for CLV.
        taken_amer = ""

    closing_line = ""
    close_taken = ""
    close_other = ""
    result = "pending"

    if market == "spread":
        which = side_home_away(side, home, away)
        if which is None:
            return {}, f"{leg_id}: skip — side {side!r} not in {away}@{home}", False
        sl = _f(game.get("spread_line"))
        if sl is None:
            return {}, f"{leg_id}: skip — missing spread_line for {game_id}", False
        closing_line = _fmt_line(closing_spread_line(sl, which))
        if which == "home":
            close_taken = _american_str(game.get("home_spread_odds"))
            close_other = _american_str(game.get("away_spread_odds"))
        else:
            close_taken = _american_str(game.get("away_spread_odds"))
            close_other = _american_str(game.get("home_spread_odds"))
        if line_at_take is None:
            return {}, f"{leg_id}: skip — missing line_at_take for spread", False
        result = grade_spread(which, line_at_take, home_score, away_score)

    elif market == "total":
        tl = _f(game.get("total_line"))
        if tl is None:
            return {}, f"{leg_id}: skip — missing total_line for {game_id}", False
        closing_line = _fmt_line(tl)
        s = side.lower()
        if s == "over":
            close_taken = _american_str(game.get("over_odds"))
            close_other = _american_str(game.get("under_odds"))
        elif s == "under":
            close_taken = _american_str(game.get("under_odds"))
            close_other = _american_str(game.get("over_odds"))
        else:
            return {}, f"{leg_id}: skip — total side must be over|under, got {side!r}", False
        if line_at_take is None:
            return {}, f"{leg_id}: skip — missing line_at_take for total", False
        result = grade_total(s, line_at_take, home_score, away_score)

    elif market == "ml":
        which = side_home_away(side, home, away)
        if which is None:
            return {}, f"{leg_id}: skip — side {side!r} not in {away}@{home}", False
        closing_line = ""
        if which == "home":
            close_taken = _american_str(game.get("home_moneyline"))
            close_other = _american_str(game.get("away_moneyline"))
        else:
            close_taken = _american_str(game.get("away_moneyline"))
            close_other = _american_str(game.get("home_moneyline"))
        result = grade_ml(which, home_score, away_score)

    else:
        return {}, f"{leg_id}: skip — market {market!r} not handled for closes", False

    close_dec = ""
    if close_taken:
        try:
            close_dec = f"{lib.american_to_decimal(close_taken):.6f}".rstrip("0").rstrip(
                "."
            )
        except (ValueError, TypeError):
            close_dec = ""

    clv = compute_clv(taken_amer, close_taken, close_other)

    updates = {
        "closing_data_available": "true",
        "closing_line": closing_line,
        "closing_price_american": close_taken,
        "closing_price_decimal": close_dec,
        "clv_no_vig": clv,
        "result": result,
    }
    return updates, f"{leg_id}: updated {market} {game_id} → {result}", True


def apply_refresh(
    legs: list[dict[str, str]],
    games: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str], int, int]:
    """Apply closing updates. Returns (legs, log_lines, updated_n, skipped_n)."""
    by_id = index_games(games)
    fieldnames = list(legs[0].keys()) if legs else []
    # Ensure writable cols exist in fieldnames order from existing header
    log: list[str] = []
    updated = 0
    skipped = 0
    out: list[dict[str, str]] = []
    for leg in legs:
        updates, reason, did = process_leg(leg, by_id)
        new_leg = dict(leg)
        if did and updates:
            for k, v in updates.items():
                if k in WRITABLE:
                    new_leg[k] = v
            updated += 1
        else:
            skipped += 1
        log.append(reason)
        out.append(new_leg)
    return out, log, updated, skipped


def write_legs(path: Path, legs: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in legs:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def refresh_one(
    legs_path: Path,
    games: list[dict[str, str]],
    *,
    dry_run: bool,
    label: str,
) -> tuple[int, int]:
    """Refresh closing fields on one legs-like CSV. Returns (updated, skipped)."""
    if not legs_path.exists():
        print(f"{label}: skip — missing {legs_path}")
        return 0, 0
    with legs_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        legs = list(reader)

    new_legs, log, updated, skipped = apply_refresh(legs, games)
    print(f"--- {label} ({legs_path.name}) ---")
    for line in log:
        print(line)
    print(f"summary [{label}]: updated={updated} skipped={skipped} total={len(legs)}")

    if dry_run:
        print(f"dry-run [{label}]: no write")
        return updated, skipped

    write_legs(legs_path, new_legs, fieldnames)
    print(f"wrote {legs_path}")
    return updated, skipped


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--refresh",
        action="store_true",
        required=True,
        help="Refresh closing_* columns (Tue after week final only)",
    )
    p.add_argument(
        "--games-csv",
        default="",
        help="Optional local games.csv path (tests); default: fetch nflverse URL",
    )
    p.add_argument(
        "--legs",
        default=str(LEGS),
        help="Path to legs.csv",
    )
    p.add_argument(
        "--shadow-legs",
        default=str(SHADOW_LEGS),
        help="Path to shadow_legs.csv (same closing rules as legs)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute updates but do not write CSVs",
    )
    args = p.parse_args(argv)

    if args.games_csv:
        games_text = Path(args.games_csv).read_text(encoding="utf-8")
        games = load_games_from_text(games_text)
    else:
        print(f"Fetching {NFLVERSE_GAMES_URL} …")
        games = fetch_games_csv()

    refresh_one(Path(args.legs), games, dry_run=args.dry_run, label="taken")
    refresh_one(
        Path(args.shadow_legs), games, dry_run=args.dry_run, label="shadow"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
