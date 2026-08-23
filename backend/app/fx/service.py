from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Tuple

from app.fx.client import get_fx_client


def convert(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    """Convert a single amount between currencies, rounded to cents."""
    if from_currency == to_currency:
        return amount
    rate = get_fx_client().get_rate(from_currency, to_currency)
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sum_converted(rows: Iterable[Tuple[Decimal, str]], to_currency: str) -> Decimal:
    """Sum a sequence of (amount, currency) pairs, converting each into
    to_currency first. This is the only correct way to total mixed-currency
    amounts — a SQL-level SUM() across rows in different currencies silently
    adds incompatible units together."""
    client = get_fx_client()
    rate_cache = {}
    total = Decimal("0.00")
    for amount, currency in rows:
        if currency == to_currency:
            total += amount
            continue
        if currency not in rate_cache:
            rate_cache[currency] = client.get_rate(currency, to_currency)
        total += amount * rate_cache[currency]
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
