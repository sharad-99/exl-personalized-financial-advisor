"""Exact monetary helpers. Money is Decimal at the edges and integer paise inside
vectorised analytics, so no float ever touches a monetary value."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Decimal | int | str) -> Decimal:
    """Normalise to 2 decimal places using banker-friendly HALF_UP rounding."""
    if isinstance(value, float):  # pragma: no cover - defensive; floats are a programming error
        raise TypeError("Monetary values must not be floats")
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_paise(value: Decimal) -> int:
    return int((to_money(value) * 100).to_integral_value())


def from_paise(paise: int) -> Decimal:
    return (Decimal(int(paise)) / 100).quantize(TWO_PLACES)


def safe_ratio(numerator: Decimal, denominator: Decimal, places: str = "0.0001") -> Decimal | None:
    """Ratio with explicit None when undefined (never silently 0)."""
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(Decimal(places), rounding=ROUND_HALF_UP)
