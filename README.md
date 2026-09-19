# nfl-ledger

Source of truth for Erik’s NFL betting process. **Anything not in `data/tickets.csv` and `data/legs.csv` did not happen as a take.** Graded-but-not-taken decisions live in the **shadow book** (`data/shadow.csv` + `data/shadow_legs.csv`) — never invent historical PASS rows. Chat, Slack, cards, and summaries are not records.

Research and alerts only. **Bots never place bets.** Stakes are Erik’s call. Takes only at **DraftKings (DK)** and **Hard Rock (HR)**. **BettorEdge (BE)** is research / comparison only.

---

## Who does what

| Role | Job |
| --- | --- |
| **Chief of Staff** | Merge layer. Locks protocol, routes Erik-facing updates (Topic · What’s going on · Why · What Erik needs). Logs `stake_vs_grade=override` when money went against the grade — unprompted, unsmoothed. Alert routing (in-app until Quo A2P Approved). |
| **NFL Manager** | Owns the NFL lane. Relays protocol to bots; coordinates SCREEN → GRADE → take → ledger. |
| **NFL Scout** | **SCREEN** mode only: finds candidates (S1–S5). Never grades, never assigns PLAY/ENTERTAINMENT/PASS, never sets stakes. |
| **Edge Analyst** | **GRADE** mode only: grades SCREEN handoffs. Never invents candidates. Issues PLAY / PASS / ENTERTAINMENT / UNGRADED / LOTTERY labels per rules. |
| **Odds Watch** | Live line movement / book prices for watches (DK+HR). Feeds screens and cover watches. |
| **Bet Simulator** | Tracks locked ticket stakes and structure for a slate (what was “locked” for sweat). Not the ledger. |
| **Loss Minimizer** | In-game hedge / cash-out alerts when the cover is **clear**. Not every play. Never places. |

Skills (Grok Bot): `nfl-screen-mode`, `sgp-edge-rules`, `nfl-ledger-protocol`.

---

## End-to-end process

```
Slate → SCREEN (Scout) → GRADE (Edge) → Erik decides stake
      → log take OR shadow (no-go) in this repo (PR) at decision time
      → watch (Odds Watch / Loss Minimizer)
      → settle (PR) → Tuesday close_lines.py → Monday report
```

1. **SCREEN** — Scout runs `screen <day|slate>` over DK+HR (both sides of markets). Cap 8 S1–S4 candidates → “Hand to GRADE.” S5 is a separate lottery construction.
2. **GRADE** — Edge grades only those candidates (INPUT GATE first).
3. **Take** — Erik places at DK or HR. Chief/Manager open a **take** PR into `tickets.csv` + `legs.csv` **at or before** placement (never after the outcome).
4. **Shadow (no-go)** — When Edge issues **PASS**, or Erik skips a **PLAY** / **ENTERTAINMENT**, Chief/NFL Manager logs a **shadow** PR into `shadow.csv` + `shadow_legs.csv` **at decision time** with both-side prices — never after the outcome. Default `paper_stake_usd` = **$10** (hard-coded; no other unit size). Do **not** backfill old PASSes.
5. **Watch** — alerts in-app / Chief only until Quo SMS is Approved (no Slack until then).
6. **Settle** — after the game, **settle** PR fills `settled`, `returned_usd`, `settled_at`, leg `result` (taken and/or shadow).
7. **Close** — Tuesday after the week is final: `python scripts/close_lines.py --refresh` only (never earlier). Refreshes `legs.csv` **and** `shadow_legs.csv`.
8. **Report** — Monday: `python scripts/monday_report.py` (includes **Taken vs shadow**). Outcome ≠ proof of grade quality.

---

## SCREEN (Scout)

Trigger: `screen <day or slate>`.

### Per game first
```
fav_derived = (total + |spread|) / 2
dog_derived = (total - |spread|) / 2
```

### S1–S4 → hand to GRADE
| Tag | Rule |
| --- | --- |
| **S1 Correlated pair** | Only if `3 ≤ \|spread\| ≤ 7`. Exactly two candidates: fav cover + over; dog cover + under. Max 2 legs. |
| **S2 Boost flip** | Promo moves a main-line market from minus → plus. Single leg; record pre/post, cap, cash-out terms. |
| **S3 Soft team total** | Posted TT more than **1.0** from derived. Single leg; both prices. |
| **S4 Route** | Same **identical** line, priced **≥10¢** apart across DK/HR. Not a ticket — routing note. Half-point line differ → no route. Cents: minus distance to −100; plus distance from +100; −105 to +102 = 7¢. |

Hard rules: max 2 legs per S1–S4 candidate; no narrative/trends; cap 8; “no candidates” is valid.

### S5 LOTTERY (cross-game)
Label is **LOTTERY** only (never PLAY / ENTERTAINMENT). Own weekly budget (set before the board). Max one S5/week unless raised. Never resize up.

- **3–5 legs**, one per game; main-line spreads/totals only; no ML shorter than −150; no props / team totals / alts.
- Both sides locked at the **placing** book; shop the **whole ticket**.
- Rank by lowest de-vig hold; user-chosen legs honored with no story attached.
- Gates: `exp_return ≥ 0.75`; per-leg hold ≤ **3pp**.
- One timestamped snapshot; re-verify mains before ladder; mandatory BE comparison table (research); liquidity feeds `r`; one DK ladder per pass.

**S5 ticket math**
```
fair_i     = de-vigged P(leg i)
fair_ticket = ∏ fair_i
multiple   = offered payout including stake
exp_return = fair_ticket × multiple     # per $1
cost_pct   = 1 − exp_return
```
Print expect $ back per $10, cost %, stake → $ cost for the shot.

**Houser-derived BE comparison (research rows, not default POST)**  
Default target houser return `r = 1%` until calibrated from filled BE parlays (median ROI by leg count, n≥10).
```
m = r(1−p) / (p+r)
M = (1−m) / p
user_expect = (1−m)(1−fee)    # fee basis + URL this pass only
```
Rows for legs 2–5: p, M, m, liability, houser ROI, BE expect, DK expect, winner (BE/DK/tie within $0.10).

---

## GRADE (Edge Analyst)

Never invents candidates. Math stays exact — no alternate formulas.

### INPUT GATE
Every leg needs a **locked price on both sides** at a named book. Else only:
```
UNGRADED · <game> · <legs> · missing: …
qualifies as ENTERTAINMENT if combo ≥ <threshold>x
```
Threshold = multiple where offered implied = **conservative fair + 4pp** (from leg probs; no live combo needed).  
UNGRADED: no %, gap, cost, ranking, or “best.” No “provisional/proxy/estimated.”

### Core conversions
**American → implied**
- Negative: `|odds| / (|odds| + 100)`  
- Positive: `100 / (odds + 100)`

**De-vig:** both sides’ implied ÷ sum → fair probabilities.

**Gap** (graded): offered implied − fair (positive = overpaying).

### Rules 1–7 (summary)
1. Always show offered vs fair (and gap).  
2. Derive TT before any team-score leg (`fav/dog` as above).  
3. Flag restating legs.  
4. **Conservative** = product of de-vigged legs (working fair). **Generous** ≈ conservative × 1.4 for tight **same-game** legs — **reject only**. Expected cost / PLAY / ENTERTAINMENT use conservative. Offered beating generous → recheck inputs, not PLAY.  
5. Aggregate shared-leg exposure across tickets; script ≤ half entertainment budget.  
6. Better outside price = **routing (where)**, never veto (whether).  
7. No trend without a mechanism.

### Verdicts
| Label | Meaning |
| --- | --- |
| **UNGRADED** | Failed INPUT GATE |
| **PASS** | Graded; no edge / hard ban (gap vs conservative > **10pp**, or implied > generous) |
| **PLAY** | Edge vs conservative; routed; not hard-banned |
| **ENTERTAINMENT** | Within **4pp** of conservative; stake in night budget; script ≤ half; `expected cost = stake × gap_conservative` |
| **LOTTERY** | S5 only — see SCREEN |

Graded line format (malformed if incomplete):  
`label · offered · fair · gap · cost · stake`

---

## Ledger protocol (this repo)

### Recording a take
1. Log **at or before** placement — never after the outcome.  
2. Required: `placed_at` (minute + UTC offset), `book`, `lane`, `stake_usd`, per-leg `price_at_take` / `line_at_take` (taken side), `edge_grade_at_placement`.  
3. Unknown → blank + dated `VERIFY(YYYY-MM-DD):` in notes — never guess, never wait.  
4. `edge_grade_at_placement` = what Edge issued (incl `UNGRADED`) — never upgrade to match stake.  
5. `stake_vs_grade=override` whenever money went against the grade. A ledger that is always `agree` is managed, not kept.  
6. Copy money from the **slip labels**: DK “To Win” → `to_win_usd`; DK “Payout” → `payout_usd`. Do not swap them. See [Money columns](#money-columns-stake_usd-to_win_usd-payout_usd).

### VERIFY notes
- Format: `VERIFY(YYYY-MM-DD): …` (date required). Older than **7 days** (America/New_York) → validate error.  
- **Never excused by VERIFY** on at-placement takes: ticket `placed_at`; leg `game_id`; leg price (`price_at_take` or `american_price_at_take`). Blank = hard fail.  
- **RECONSTRUCTED exception:** a row marked `RECONSTRUCTED` with dated `VERIFY(YYYY-MM-DD):` may leave those three blank (do not invent). Counts as VERIFY-debt.
- Other required blanks may be excused by VERIFY only while parent ticket `status=open` **and** kickoff has not passed (min `kickoff_at` across that ticket’s legs; if all blank, open status alone still allows the excuse). After any kickoff has passed, or `status` is `settled`|`void`|`cashout`, VERIFY excuses nothing.  
- `validate.py` always prints a **VERIFY-debt** count (rows still carrying a dated VERIFY note).

### Reconstructions
Chat/Slack backfills are marked `RECONSTRUCTED (…, not at-placement)` in notes. Reconstructions may be **corrected in place** until the first true at-placement take is logged for that ticket; after that, frozen-field rules apply. Unknown hard fields on a reconstructed row stay blank + dated VERIFY — never invent a `game_id`, price, or `placed_at` to satisfy validate. Never invent `to_win_usd` or `payout_usd` from chat estimates either.

### Frozen fields
Never edit on an existing row: `placed_at`, `book`, `lane`, `stake_usd`, `edge_grade_at_placement`, `stake_vs_grade`, `price_at_take`, `line_at_take`, `game_id`.  
Wrong value → **append a new row** that references the original in `notes`. The error stays; the error is data.

May fill later: `settled`, `returned_usd`, `settled_at`, closing columns via `close_lines.py` only.

### Closing data
`anytime_td` / `first_td`: `closing_data_available=false` **forever**. No estimated closes from any board. If a lane has no closing source, say so every time it is proposed.

### Reporting
Outcome is not evidence. A loser that beat the close was a good take; a winner taken worse than the close was a bad take that got paid. Never treat W/L as validation of a grade. No retro “should have hit” narratives.

### Research
Do not mine nflverse for Edge angles. Hypothesis logged **before** test; must clear vig by a real margin. Search-found patterns are noise until out-of-sample.

---

## Data schema (v0)

### `data/tickets.csv`
`ticket_id,placed_at,book,lane,market_family,stake_usd,to_win_usd,payout_usd,american_price,decimal_price,edge_grade_at_placement,stake_vs_grade,status,settled,returned_usd,settled_at,notes,created_at,updated_at`

Enums: `book` DK|HR|OTHER · `lane` TNF|S5|ATD|SCREEN|SGP|OTHER · `market_family` SPREAD_TOTAL|SGP|ATD|PARLAY|OTHER · `edge_grade_at_placement` PLAY|ENTERTAINMENT|LOTTERY|PASS|UNGRADED|HOLD|OTHER · `stake_vs_grade` agree|override · `status` open|settled|void|cashout

### Money columns (`stake_usd`, `to_win_usd`, `payout_usd`)

| Column | Meaning | Match this on a DK slip |
| --- | --- | --- |
| `stake_usd` | Amount risked | Stake / risk |
| `to_win_usd` | Profit if the ticket wins (**excludes** stake) | **To Win** |
| `payout_usd` | Stake + profit if the ticket wins (**includes** stake) | **Payout** |

- If both `to_win_usd` and `payout_usd` are filled, `payout_usd` ≈ `stake_usd + to_win_usd` within **$0.01**.
- Never invent either from chat, Slack, or estimates. Unknown → blank + dated `VERIFY(YYYY-MM-DD):` and wait for Erik’s slip.
- Arithmetic-only fill: if **one** of `to_win_usd` / `payout_usd` is filled and the other is blank, you may fill the blank from `stake_usd` plus the filled column. Do **not** guess which DK label the filled number was. If it could be either To Win or Payout, leave the other blank.
- `monday_report.py` infers a parlay multiple from `payout_usd / stake_usd` when ticket american/decimal is missing — `payout_usd` must stay stake-inclusive.

### `lane` vs `market_family` (`SGP` vs `PARLAY`)

`lane` is **which process lane built the ticket**. `market_family` is **ticket structure**. Do not treat them as synonyms.

| Value | Use |
| --- | --- |
| `market_family=SGP` | Same-game parlay: every leg shares one `game_id` (e.g. spread + total on the same game). |
| `market_family=PARLAY` | Multi-game parlay (S5 cross-game; legs from different games). |
| `market_family=ATD` | Anytime-TD ticket. |
| `market_family=SPREAD_TOTAL` | Straight / correlated pair not built as an SGP. |
| `lane=S5` | Lottery construction (SCREEN S5). **Not** the same as SGP. S5 tickets are usually `market_family=PARLAY`. |
| `lane=SGP` | Same-game graded tickets in the SGP process lane. |
| `lane=TNF` | Thursday / TNF process lane. Structure is still `market_family` — a TNF same-game spread+total is `SGP`, not `PARLAY`. |

Going forward: do not put S5 lottery tickets in `market_family=SGP`. Do not label a same-game ticket `PARLAY`. Do **not** relabel historical rows solely for neatness — fix `RECONSTRUCTED` `market_family` only with slip evidence, noted as a RECONSTRUCTED exception.

### Seed reconstructions (2026-09-17)

Documented, not rewritten. No invented `placed_at`, prices, or `game_id`.

1. **TNF** `4500ac74-…` — `lane=TNF`, `market_family=SGP`. Legs are BUF −5.5 + Over 54.5, both DET@BUF. **SGP is correct** (same-game spread+total). Money: `stake_usd=29.86`, `to_win_usd=70.14`, `payout_usd=100` (29.86 + 70.14 = 100.00). No CSV change.
2. **S5** `bd4ecb98-…` — `lane=S5`, `market_family=PARLAY`. Legs ARI / IND / CIN (cross-game). **PARLAY is correct.** Recorded money already satisfies payout = stake + to_win (`9.87 + 61.13 = 71`). Notes still flag slip wording (~71–78 “to-win” vs recorded `payout_usd=71`) as VERIFY — do not rewrite without Erik’s slip.
3. **ATD** `f0840775-…` — `to_win_usd` and `payout_usd` **left blank**. Backfill waits for Erik’s slip. Do not invent from chat ~+205.

### `data/legs.csv`
`leg_id,ticket_id,game_id,kickoff_at,away_team,home_team,market,side,line_at_take,price_at_take,american_price_at_take,decimal_price_at_take,closing_data_available,closing_line,closing_price_american,closing_price_decimal,clv_no_vig,result,notes`

Enums: `market` spread|total|ml|anytime_td|first_td|team_total|other · `result` pending|win|loss|push|void|(blank)

### `data/shadow.csv` (no-go / paper book)
Header-only until Edge logs a decision. **Never invent historical PASS tickets.**

`shadow_id,decided_at,book,lane,market_family,edge_grade,paper_stake_usd,offered_american,offered_decimal,fair_conservative,gap_pp,reason_not_taken,status,settled,returned_usd,settled_at,notes,created_at,updated_at`

Enums: `book` DK|HR|OTHER · `lane` TNF|S5|ATD|SCREEN|SGP|OTHER · `edge_grade` PLAY|PASS|ENTERTAINMENT|UNGRADED|LOTTERY|HOLD|OTHER · `reason_not_taken` pass_edge|skip_entertainment|skip_play|budget|user|other · `status` open|settled|void|expired

**`paper_stake_usd` default = `10`** (hard-coded unit size for every new shadow row — do not use another size). `decided_at` is always required (decision log; VERIFY never excuses it).

### `data/shadow_legs.csv`
Mirrors `legs.csv` fields needed for close/CLV:

`leg_id,shadow_id,game_id,kickoff_at,away_team,home_team,market,side,line_at_take,price_at_take,american_price_at_take,decimal_price_at_take,closing_data_available,closing_line,closing_price_american,closing_price_decimal,clv_no_vig,result,notes`

Same ATD rule: `anytime_td` / `first_td` → `closing_data_available=false` forever.

### Shadow logging rules
1. Log **at decision time** when Edge issues PASS, or Erik skips PLAY/ENTERTAINMENT — never after the outcome.
2. Capture **both-side prices** (and fair/gap when graded) on the shadow row / legs.
3. Chief of Staff / NFL Manager owns the shadow PR (same merge layer as takes).
4. Empty file = headers only until the first real decision is logged.
5. Monday report section **Taken vs shadow** compares taken portfolio vs graded-but-not-taken paper P&L/CLV.

---

## Git workflow

See `CONTRIBUTING.md`. **PRs only.** One event type per PR: take | shadow | settle | close | report | fix | docs.  
No direct push to `main`, no `--amend`, no rebase of merged history, no force push, no file deletion.

`validate.py` lives at the **repo root**. Run it before opening a PR. CI (`.github/workflows/validate.yml`) runs `python validate.py` and `python -m unittest discover -s tests` on every pull request and every push to `main`.

```bash
python validate.py
python -m unittest discover -s tests
python scripts/close_lines.py --refresh   # Tuesday after week final ONLY
python scripts/monday_report.py           # Mondays
```

## Budgets (`config.json`)

Placeholder night / weekly caps for process (not ticket values). Adjust before the board. Do not invent `stake_usd` from these.

| Field | Meaning | Placeholder |
| --- | --- | --- |
| `entertainment_budget_usd` | Night entertainment budget (example) | `100` |
| `script_cap_usd` | Script ≤ half entertainment | `50` |
| `s5_weekly_cap_usd` | S5 lottery weekly cap | `10` |
| `lane_budgets_usd` | Per-lane weekly placeholders (`null` = not set) | S5=`10`; others `null` |

---

## Jobs / calendars

| When | What |
| --- | --- |
| Thu 12:00 ET | Midday spread/total snapshot (scorebook baseline) |
| Sun (armed watches) | S5 / open-ticket cover watch — actionable hedges only |
| Mon ~10:00 ET | Scorecard / `monday_report.py` |
| Tue after week final | `close_lines.py --refresh` |

Alert delivery: **in-app / Chief** until Quo A2P is Approved; then Quo SMS (+ optional Slack). No Slack while Quo is pending.

---


---

## Close lines & Monday report

```bash
# Tuesday after the week is final ONLY — refuses games without a final score
python scripts/close_lines.py --refresh

# Monday scorecard (pass season/week, or omit to derive from leg game_ids)
python scripts/monday_report.py --season 2026 --week 2
python scripts/monday_report.py --season 2026 --week 2 --write   # also reports/YYYY_WW.md
```

Shared odds math lives in `lib.py` (same formulas as GRADE). **`clv_no_vig` sign:** `fair_taken_at_close − offered_implied_at_take` — **positive = beat the close** (good take); negative = worse than the close. Fair close always uses de-vig of **both** close sides; never one-sided raw implied. `anytime_td` / `first_td` stay permanently unauditable (`closing_data_available=false`).

`close_lines.py --refresh` also refreshes `data/shadow_legs.csv` with the same refuse-without-final and ATD rules. Monday report includes **Taken vs shadow** (taken stake/returns vs shadow paper-$10 counts by grade, settled paper P&L, and mean CLV on auditable legs).

## Unchange

Never place bets. DK+HR takes. BE research only. Loss Minimizer: clear hedge/cash-out only. Stakes are Erik’s.
