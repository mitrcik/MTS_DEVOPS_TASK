from __future__ import annotations

from decimal import Decimal

import pytest

from mts_api.tariffs import CATALOG, UnknownTariffError, calculate_quote, get_tariff


def amounts(quote: dict) -> dict[str, str]:
    return {line["item"]: line["amount"] for line in quote["breakdown"]}


def test_within_package_costs_only_monthly_fee() -> None:
    quote = calculate_quote(
        get_tariff("basic"), minutes=300, sms=50, data_gb=Decimal("10"), roaming_days=0
    )
    assert quote["total"] == "300.00"
    assert amounts(quote)["extra_minutes"] == "0.00"


def test_overage_is_charged_per_unit() -> None:
    # basic: 300 + 20 мин * 2.50 + 5 SMS * 2.00 + 1.5 ГБ * 50.00 + 2 дня * 250.00
    quote = calculate_quote(
        get_tariff("basic"), minutes=320, sms=55, data_gb=Decimal("11.5"), roaming_days=2
    )
    lines = amounts(quote)
    assert lines["extra_minutes"] == "50.00"
    assert lines["extra_sms"] == "10.00"
    assert lines["extra_data_gb"] == "75.00"
    assert lines["roaming_days"] == "500.00"
    assert quote["total"] == "935.00"


def test_unlimited_data_has_no_data_overage() -> None:
    quote = calculate_quote(
        get_tariff("unlimited"), minutes=0, sms=0, data_gb=Decimal("9999.99"), roaming_days=0
    )
    assert amounts(quote)["extra_data_gb"] == "0.00"
    assert quote["total"] == "990.00"


def test_rounding_is_half_up_to_cents() -> None:
    quote = calculate_quote(
        get_tariff("smart"), minutes=800, sms=200, data_gb=Decimal("35.01"), roaming_days=0
    )
    # 0.01 ГБ * 40.00 = 0.40
    assert amounts(quote)["extra_data_gb"] == "0.40"
    assert quote["total"] == "650.40"


def test_negative_usage_is_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_quote(
            get_tariff("basic"), minutes=-1, sms=0, data_gb=Decimal("0"), roaming_days=0
        )


def test_unknown_tariff() -> None:
    with pytest.raises(UnknownTariffError):
        get_tariff("does-not-exist")


def test_catalog_ids_are_url_safe() -> None:
    for tariff_id in CATALOG:
        assert tariff_id == tariff_id.lower()
        assert all(ch.isalnum() or ch == "-" for ch in tariff_id)
