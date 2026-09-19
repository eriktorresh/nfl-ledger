# Contributing

This repo is the source of truth. Chat, Slack, cards, and summaries are not records. Anything not in `data/tickets.csv` + `data/legs.csv` did not happen as a take. Graded-but-not-taken decisions live in the shadow book.

## How changes land

- **PRs only.** No direct push to `main`.
- **One event type per PR:** `take` | `shadow` | `settle` | `close` | `report` | `fix` | `docs`.
- Do not force-push, `--amend`, or rebase merged history. Do not delete files.

## Before you open a PR

Run from the repo root:

```bash
python validate.py
```

Must exit 0. CI (`.github/workflows/validate.yml`) runs the same command plus `python -m unittest discover -s tests` on every pull request and every push to `main`. Fail on non-zero.

Optional locally:

```bash
python -m unittest discover -s tests
```

## Never invent

Do not invent `game_id`, prices (`price_at_take` / `american_price_at_take`), or `placed_at`.

Unknown → leave blank and add a dated `VERIFY(YYYY-MM-DD):` note, or wait for Erik’s slip. Do not guess to satisfy validate.

On at-placement takes, VERIFY never excuses: ticket `placed_at`, leg `game_id`, and at least one of `price_at_take` or `american_price_at_take`. Blank = hard fail.

## Frozen fields

Never edit these on an existing row:

`placed_at`, `book`, `lane`, `stake_usd`, `edge_grade_at_placement`, `stake_vs_grade`, `price_at_take`, `line_at_take`, `game_id`.

Wrong value → **append a new row** that references the original in `notes`. The error stays; the error is data.

**RECONSTRUCTED exception:** seed / chat-backfill rows marked `RECONSTRUCTED` may be corrected **in place** until the first true at-placement take is logged for that ticket. After that, frozen-field append-correct applies. Do not invent blanks on reconstructed rows — dated VERIFY only.

May fill later: `settled`, `returned_usd`, `settled_at`, closing columns via `scripts/close_lines.py` only.

## Event types

| Type | What |
| --- | --- |
| **take** | Log a placed ticket in `data/tickets.csv` + `data/legs.csv` at or before placement |
| **shadow** | Log a no-go in `data/shadow.csv` + `data/shadow_legs.csv` at decision time |
| **settle** | Fill `settled` / `returned_usd` / `settled_at` / leg `result` after the game |
| **close** | Tuesday `python scripts/close_lines.py --refresh` only (never earlier) |
| **report** | Monday `python scripts/monday_report.py` |
| **fix** | Validator / protocol / CI / data-quality (not a take or settle) |
| **docs** | README, CONTRIBUTING, templates, config placeholders |

## VERIFY notes

Format: `VERIFY(YYYY-MM-DD): …` (date required). Older than **7 days** (America/New_York) → validate error.

## History

No force push, no amend of merged commits, no file deletion.
