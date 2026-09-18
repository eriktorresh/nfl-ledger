# nfl-ledger

Source of truth for Erik’s NFL betting process. **Anything not in `data/tickets.csv` and `data/legs.csv` did not happen.** Chat, Slack, cards, and summaries are not records.

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
      → log take in this repo (PR) at/before placement
      → watch (Odds Watch / Loss Minimizer)
      → settle (PR) → Tuesday close_lines.py → Monday report
```

1. **SCREEN** — Scout runs `screen <day|slate>` over DK+HR (both sides of markets). Cap 8 S1–S4 candidates → “Hand to GRADE.” S5 is a separate lottery construction.
2. **GRADE** — Edge grades only those candidates (INPUT GATE first).
3. **Take** — Erik places at DK or HR. Chief/Manager open a **take** PR into `tickets.csv` + `legs.csv` **at or before** placement (never after the outcome).
4. **Watch** — alerts in-app / Chief only until Quo SMS is Approved (no Slack until then).
5. **Settle** — after the game, **settle** PR fills `settled`, `returned_usd`, `settled_at`, leg `result`.
6. **Close** — Tuesday after the week is final: `python scripts/close_lines.py --refresh` only (never earlier).
7. **Report** — Monday: `python scripts/monday_report.py`. Outcome ≠ proof of grade quality.

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

### VERIFY notes
- Format: `VERIFY(YYYY-MM-DD): …` (date required). Older than **7 days** (America/New_York) → validate error.  
- **Never excused by VERIFY** on at-placement takes: ticket `placed_at`; leg `game_id`; leg price (`price_at_take` or `american_price_at_take`). Blank = hard fail.  
- **RECONSTRUCTED exception:** a row marked `RECONSTRUCTED` with dated `VERIFY(YYYY-MM-DD):` may leave those three blank (do not invent). Counts as VERIFY-debt.
- Other required blanks may be excused by VERIFY only while parent ticket `status=open` **and** kickoff has not passed (min `kickoff_at` across that ticket’s legs; if all blank, open status alone still allows the excuse). After any kickoff has passed, or `status` is `settled`|`void`|`cashout`, VERIFY excuses nothing.  
- `validate.py` always prints a **VERIFY-debt** count (rows still carrying a dated VERIFY note).

### Reconstructions
Chat/Slack backfills are marked `RECONSTRUCTED (…, not at-placement)` in notes. Reconstructions may be **corrected in place** until the first true at-placement take is logged for that ticket; after that, frozen-field rules apply. Unknown hard fields on a reconstructed row stay blank + dated VERIFY — never invent a `game_id`, price, or `placed_at` to satisfy validate.

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

### `data/legs.csv`
`leg_id,ticket_id,game_id,kickoff_at,away_team,home_team,market,side,line_at_take,price_at_take,american_price_at_take,decimal_price_at_take,closing_data_available,closing_line,closing_price_american,closing_price_decimal,clv_no_vig,result,notes`

Enums: `market` spread|total|ml|anytime_td|first_td|team_total|other · `result` pending|win|loss|push|void|(blank)

---

## Git workflow

- **PRs only** for take | settle | close | report (one PR per event).  
- No direct push to `main` for those events, no `--amend`, no rebase of merged history, no force push, no file deletion.  
- Scaffold / docs PRs OK when labeled clearly.  
- `python validate.py` must pass before merge.

```bash
python validate.py
python tests/test_validate.py             # or: python -m unittest discover -s tests
python scripts/close_lines.py --refresh   # Tuesday after week final ONLY
python scripts/monday_report.py           # Mondays
```

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

## Unchange

Never place bets. DK+HR takes. BE research only. Loss Minimizer: clear hedge/cash-out only. Stakes are Erik’s.
