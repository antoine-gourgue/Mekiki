from decimal import Decimal

import pytest

from mekiki_engine.costing.money import jpy_to_cents, split_cents, to_cents


def test_to_cents_rounds_half_up() -> None:
    assert to_cents(Decimal("1.005")) == 101
    assert to_cents(Decimal("1.004")) == 100
    assert to_cents(Decimal("47.0588")) == 4706


def test_jpy_to_cents_uses_the_lot_rate() -> None:
    assert jpy_to_cents(8000, Decimal(170)) == 4706
    assert jpy_to_cents(0, Decimal(170)) == 0


def test_jpy_to_cents_rejects_a_non_positive_rate() -> None:
    with pytest.raises(ValueError):
        jpy_to_cents(100, Decimal(0))


@pytest.mark.parametrize(
    ("total", "weights"),
    [
        (2353, [8000] * 10),
        (1, [1, 1, 1]),
        (9999, [3, 7, 11, 13]),
        (98823, [1200, 450, 8000, 300, 300, 15000, 7]),
        (0, [5, 5]),
        (7, [0, 0, 1]),
    ],
)
def test_split_cents_always_adds_up_to_the_total(total: int, weights: list[int]) -> None:
    parts = split_cents(total, weights)
    assert sum(parts) == total
    assert len(parts) == len(weights)
    assert all(p >= 0 for p in parts)


def test_split_cents_is_proportional() -> None:
    assert split_cents(1000, [1, 3]) == [250, 750]


def test_split_cents_gives_nothing_to_zero_weights() -> None:
    assert split_cents(100, [0, 1, 0]) == [0, 100, 0]


def test_split_cents_falls_back_to_an_even_split_when_all_weights_are_zero() -> None:
    assert split_cents(10, [0, 0, 0]) == [4, 3, 3]


def test_split_cents_breaks_ties_in_favour_of_the_first_items() -> None:
    # 2353 / 10 = 235.3 each: the three leftover cents go to the first three cards.
    assert split_cents(2353, [8000] * 10) == [236, 236, 236] + [235] * 7


def test_split_cents_gives_leftovers_to_the_largest_remainders() -> None:
    # Exact shares are 3.33, 6.67: the leftover cent goes to the second one.
    assert split_cents(10, [1, 2]) == [3, 7]


def test_split_cents_of_nothing_is_empty() -> None:
    assert split_cents(100, []) == []


@pytest.mark.parametrize(("total", "weights"), [(-1, [1]), (10, [1, -1])])
def test_split_cents_rejects_negative_inputs(total: int, weights: list[int]) -> None:
    with pytest.raises(ValueError):
        split_cents(total, weights)
