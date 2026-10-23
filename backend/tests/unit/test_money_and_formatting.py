from decimal import Decimal

import pytest

from app.utils.dates import add_months, months_between
from app.utils.formatting import format_inr
from app.utils.money import from_paise, safe_ratio, to_money, to_paise


def test_to_money_rounds_half_up_to_two_places() -> None:
    assert to_money(Decimal("10.005")) == Decimal("10.01")
    assert to_money(Decimal("10.004")) == Decimal("10.00")
    assert to_money("3") == Decimal("3.00")


def test_floats_are_rejected_for_money() -> None:
    with pytest.raises(TypeError):
        to_money(0.1)  # type: ignore[arg-type]


def test_paise_round_trip_is_exact() -> None:
    values = [Decimal("0.10"), Decimal("0.20"), Decimal("1234567.89")]
    assert sum(to_paise(v) for v in values) == 123456819
    assert from_paise(to_paise(Decimal("0.10")) + to_paise(Decimal("0.20"))) == Decimal("0.30")


def test_safe_ratio_returns_none_instead_of_zero_for_undefined() -> None:
    assert safe_ratio(Decimal("5"), Decimal("0")) is None
    assert safe_ratio(Decimal("1"), Decimal("3")) == Decimal("0.3333")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), "Rs 0.00"),
        (Decimal("999.5"), "Rs 999.50"),
        (Decimal("1000"), "Rs 1,000.00"),
        (Decimal("123456.78"), "Rs 1,23,456.78"),
        (Decimal("12345678.9"), "Rs 1,23,45,678.90"),
        (Decimal("-2500"), "-Rs 2,500.00"),
        (None, "not available"),
    ],
)
def test_format_inr_uses_indian_grouping(value: Decimal | None, expected: str) -> None:
    assert format_inr(value) == expected


def test_month_arithmetic_clamps_month_end() -> None:
    from datetime import date

    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert months_between(date(2026, 1, 15), date(2026, 4, 14)) == 2
    assert months_between(date(2026, 1, 15), date(2026, 4, 15)) == 3
