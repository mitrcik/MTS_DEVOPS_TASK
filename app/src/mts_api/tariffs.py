"""Бизнес-логика: синтетический каталог тарифов и расчёт месячной стоимости.

Все суммы считаются в Decimal и округляются до копеек (ROUND_HALF_UP).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
CURRENCY = "RUB"


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Tariff:
    id: str
    name: str
    monthly_fee: Decimal
    included_minutes: int
    included_sms: int
    # None означает безлимитный интернет.
    included_data_gb: Decimal | None
    minute_price: Decimal
    sms_price: Decimal
    gb_price: Decimal
    roaming_day_price: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "monthly_fee": str(self.monthly_fee),
            "included": {
                "minutes": self.included_minutes,
                "sms": self.included_sms,
                "data_gb": None if self.included_data_gb is None else str(self.included_data_gb),
            },
            "overage_prices": {
                "minute": str(self.minute_price),
                "sms": str(self.sms_price),
                "gb": str(self.gb_price),
            },
            "roaming_day_price": str(self.roaming_day_price),
            "currency": CURRENCY,
        }


CATALOG: dict[str, Tariff] = {
    t.id: t
    for t in (
        Tariff(
            id="basic",
            name="Базовый (демо)",
            monthly_fee=Decimal("300.00"),
            included_minutes=300,
            included_sms=50,
            included_data_gb=Decimal("10"),
            minute_price=Decimal("2.50"),
            sms_price=Decimal("2.00"),
            gb_price=Decimal("50.00"),
            roaming_day_price=Decimal("250.00"),
        ),
        Tariff(
            id="smart",
            name="Смарт (демо)",
            monthly_fee=Decimal("650.00"),
            included_minutes=800,
            included_sms=200,
            included_data_gb=Decimal("35"),
            minute_price=Decimal("2.00"),
            sms_price=Decimal("1.50"),
            gb_price=Decimal("40.00"),
            roaming_day_price=Decimal("200.00"),
        ),
        Tariff(
            id="unlimited",
            name="Безлимитный интернет (демо)",
            monthly_fee=Decimal("990.00"),
            included_minutes=1500,
            included_sms=300,
            included_data_gb=None,
            minute_price=Decimal("1.50"),
            sms_price=Decimal("1.00"),
            gb_price=Decimal("0.00"),
            roaming_day_price=Decimal("150.00"),
        ),
    )
}


class UnknownTariffError(LookupError):
    pass


def get_tariff(tariff_id: str) -> Tariff:
    try:
        return CATALOG[tariff_id]
    except KeyError as exc:
        raise UnknownTariffError(tariff_id) from exc


def calculate_quote(
    tariff: Tariff, *, minutes: int, sms: int, data_gb: Decimal, roaming_days: int
) -> dict[str, object]:
    """Возвращает детализацию стоимости за месяц для заданного профиля потребления."""
    if minutes < 0 or sms < 0 or data_gb < 0 or roaming_days < 0:
        raise ValueError("usage values must be non-negative")

    extra_minutes = max(0, minutes - tariff.included_minutes)
    extra_sms = max(0, sms - tariff.included_sms)
    if tariff.included_data_gb is None:
        extra_gb = Decimal("0")
    else:
        extra_gb = max(Decimal("0"), data_gb - tariff.included_data_gb)

    lines = [
        ("monthly_fee", 1, tariff.monthly_fee, tariff.monthly_fee),
        ("extra_minutes", extra_minutes, tariff.minute_price, tariff.minute_price * extra_minutes),
        ("extra_sms", extra_sms, tariff.sms_price, tariff.sms_price * extra_sms),
        ("extra_data_gb", extra_gb, tariff.gb_price, tariff.gb_price * extra_gb),
        (
            "roaming_days",
            roaming_days,
            tariff.roaming_day_price,
            tariff.roaming_day_price * roaming_days,
        ),
    ]
    breakdown = [
        {
            "item": item,
            "quantity": str(qty),
            "unit_price": str(money(price)),
            "amount": str(money(amount)),
        }
        for item, qty, price, amount in lines
    ]
    total = money(sum((money(amount) for *_, amount in lines), Decimal("0")))
    return {
        "tariff_id": tariff.id,
        "currency": CURRENCY,
        "breakdown": breakdown,
        "total": str(total),
    }
