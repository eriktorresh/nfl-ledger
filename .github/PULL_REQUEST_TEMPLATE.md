## Event type

One type only:

- [ ] take
- [ ] shadow
- [ ] settle
- [ ] close
- [ ] report
- [ ] fix
- [ ] docs

## Frozen fields

- [ ] I did not edit frozen fields on an existing row (`placed_at`, `book`, `lane`, `stake_usd`, `edge_grade_at_placement`, `stake_vs_grade`, `price_at_take`, `line_at_take`, `game_id`) — or this is a `RECONSTRUCTED` seed row still eligible for in-place correction
- [ ] If a frozen value was wrong, I **append-corrected** (new row + `notes` pointing at the original) instead of editing the original
- [ ] I did not invent `game_id`, prices, or `placed_at`

## VERIFY

- [ ] Unknown fields are blank + `VERIFY(YYYY-MM-DD):` (date required), or I waited for Erik’s slip
- [ ] VERIFY date is within 7 days (America/New_York)

## Reconstruct vs append-correct

- [ ] In-place edits are only on `RECONSTRUCTED` rows that have not yet had a true at-placement log
- [ ] After the first at-placement take for a ticket, frozen-field append-correct applies

## Validate

- [ ] I ran `python validate.py` locally (must exit 0)

## Notes
