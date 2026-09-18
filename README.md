# nfl-ledger

Source of truth for Erik’s NFL takes. **Chat, Slack, and cards are not records.**

## Data

- `data/tickets.csv` — one row per ticket
- `data/legs.csv` — one row per leg (`ticket_id` FK)

Schema v0 is owned by NFL Manager / LEDGER PROTOCOL. Do not invent takes. Unknown fields: leave blank and put `VERIFY: …` in `notes`.

## Workflow

1. Log a take **at or before** placement (PR).
2. One PR per take | settle | close | report.
3. `python validate.py` must pass before merge.
4. **No direct pushes to `main`** for take/settle/close/report (PRs only). Scaffold may land on `main` once.
5. Frozen after write: `placed_at`, `book`, `lane`, `stake_usd`, `edge_grade_at_placement`, `stake_vs_grade`, `price_at_take`, `line_at_take`, `game_id`. Wrong value → append a new row referencing the original in `notes` — never edit frozen fields.
6. `scripts/close_lines.py --refresh` — **Tuesday after week final only**.
7. `scripts/monday_report.py` — Mondays.
8. `anytime_td` / `first_td`: `closing_data_available` must stay `false` forever; never fill closing_* or invent closes.
9. Bots never place bets. Books: DK / HR. BettorEdge = research only.

## Enums (tickets)

- `book`: DK | HR | OTHER
- `lane`: TNF | S5 | ATD | SCREEN | SGP | OTHER
- `market_family`: SPREAD_TOTAL | SGP | ATD | PARLAY | OTHER
- `edge_grade_at_placement`: PLAY | ENTERTAINMENT | LOTTERY | PASS | UNGRADED | HOLD | OTHER
- `stake_vs_grade`: agree | override
- `status`: open | settled | void | cashout

## Enums (legs)

- `market`: spread | total | ml | anytime_td | first_td | team_total | other
- `result`: pending | win | loss | push | void | (blank)

## Scripts

```bash
python validate.py
python scripts/close_lines.py --refresh   # Tue after week final only
python scripts/monday_report.py
```
