"""Shared odds math for GRADE and close_lines / monday_report.

Formulas match GRADE skill exactly:
- Negative American → implied = |o| / (|o| + 100)
- Positive American → implied = 100 / (o + 100)
- De-vig two-way: each implied / sum of both implieds
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

American = Union[int, str, float]


def _as_int_american(american: American) -> int:
    if isinstance(american, bool):
        raise TypeError("american odds must be int or numeric string, not bool")
    if isinstance(american, str):
        s = american.strip().replace("+", "")
        if not s:
            raise ValueError("empty american odds")
        return int(float(s)) if "." in s else int(s)
    return int(american)


def american_to_implied(american: American) -> float:
    """Convert American odds to vigged implied probability in (0, 1)."""
    o = _as_int_american(american)
    if o == 0:
        raise ValueError("american odds cannot be 0")
    if o < 0:
        ao = abs(o)
        return ao / (ao + 100.0)
    return 100.0 / (o + 100.0)


def american_to_decimal(american: American) -> float:
    """Convert American odds to decimal (European) odds."""
    o = _as_int_american(american)
    if o == 0:
        raise ValueError("american odds cannot be 0")
    if o < 0:
        return 1.0 + (100.0 / abs(o))
    return 1.0 + (o / 100.0)


def devig_two_way(
    implied_a: float, implied_b: float
) -> Tuple[float, float]:
    """Remove vig from a two-way market: fair_i = implied_i / (implied_a + implied_b)."""
    if implied_a <= 0 or implied_b <= 0:
        raise ValueError("implied probabilities must be positive")
    s = implied_a + implied_b
    if s <= 0:
        raise ValueError("sum of implieds must be positive")
    return implied_a / s, implied_b / s


def clv_no_vig(
    taken_american: American,
    close_taken_american: American,
    close_other_american: Optional[American],
) -> Optional[float]:
    """Closing-line value vs de-vigged close (taken side).

    Sign convention (documented clearly):
      CLV = fair_taken_at_close − offered_implied_at_take

    - Positive CLV ⇒ beat the close (good take: you paid less implied than
      the fair close probability of your side).
    - Negative CLV ⇒ worse than the close (bad take).
    - Zero ⇒ matched the fair close.

    fair_taken_at_close is the de-vigged probability of the taken side using
    BOTH close prices. If close_other_american is missing/blank, returns None
    (never uses raw one-sided implied as "fair").
    """
    if close_other_american is None:
        return None
    if isinstance(close_other_american, str) and not close_other_american.strip():
        return None

    offered = american_to_implied(taken_american)
    close_taken_imp = american_to_implied(close_taken_american)
    close_other_imp = american_to_implied(close_other_american)
    fair_taken, _fair_other = devig_two_way(close_taken_imp, close_other_imp)
    return fair_taken - offered
