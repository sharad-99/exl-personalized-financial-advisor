from __future__ import annotations

from decimal import Decimal

from app.utils.money import to_money


def format_inr(value: Decimal | None) -> str:
    """Format with Indian digit grouping, e.g. Decimal('1234567.5') -> 'Rs 12,34,567.50'.

    Uses the ASCII 'Rs' prefix in stored explanations so text renders everywhere;
    the frontend formats live figures with Intl (en-IN, INR).
    """
    if value is None:
        return "not available"
    money = to_money(value)
    sign = "-" if money < 0 else ""
    whole, fraction = f"{abs(money):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}Rs {whole}.{fraction}"


def format_pct(value: Decimal | None) -> str:
    return "not available" if value is None else f"{value}%"
