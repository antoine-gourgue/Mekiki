"""Money helpers.

Amounts are stored as integers in their minor unit (euro cents, yen) so that sums never
drift; ``Decimal`` is only used for intermediate maths and rounded once per component.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

HUNDRED = Decimal(100)


def to_cents(amount_eur: Decimal) -> int:
    return int(amount_eur.quantize(Decimal(1) / HUNDRED, rounding=ROUND_HALF_UP) * HUNDRED)


def jpy_to_eur(amount_jpy: int, fx_jpy_per_eur: Decimal) -> Decimal:
    if fx_jpy_per_eur <= 0:
        raise ValueError("The JPY/EUR rate must be positive.")
    return Decimal(amount_jpy) / fx_jpy_per_eur


def jpy_to_cents(amount_jpy: int, fx_jpy_per_eur: Decimal) -> int:
    return to_cents(jpy_to_eur(amount_jpy, fx_jpy_per_eur))


def percent_to_fraction(percent: Decimal) -> Decimal:
    return percent / HUNDRED


def split_cents(total_cents: int, weights: Sequence[int]) -> list[int]:
    """Split ``total_cents`` proportionally to ``weights`` without losing a cent.

    Uses the largest remainder method so the parts always add up to the total, which keeps
    a lot's allocated costs equal to what was actually paid. Zero weights everywhere fall
    back to an even split.
    """
    if not weights:
        return []
    if total_cents < 0:
        raise ValueError("Only non-negative amounts can be split.")
    if any(w < 0 for w in weights):
        raise ValueError("Weights must not be negative.")
    total_weight = sum(weights)
    effective = list(weights) if total_weight > 0 else [1] * len(weights)
    total_weight = sum(effective)

    exact = [Decimal(total_cents) * w / total_weight for w in effective]
    parts = [int(x.to_integral_value(rounding="ROUND_FLOOR")) for x in exact]
    remainder = total_cents - sum(parts)
    # Hand out the leftover cents to the largest fractional parts; ties go to the first item
    # so the result is deterministic.
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - parts[i]), i))
    for i in order[:remainder]:
        parts[i] += 1
    return parts
