"""Check the consolidated bill-history sensor against the captured bills.

Runs without a Home Assistant instance: the entity only reads coordinator.data.

Usage: python tests/sensor_shapes.py <har file>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.hygng.coordinator import HygngData  # noqa: E402
from custom_components.hygng.parser import parse_accounts, parse_bills  # noqa: E402
from custom_components.hygng.sensor import HygngBillHistorySensor  # noqa: E402


class FakeCoordinator:
    """Just enough of a coordinator for the entity properties."""

    customer_id = "148358"
    update_interval = None
    last_update_success = True

    def __init__(self, data: HygngData) -> None:
        self.data = data
        self.hass = None

    @property
    def device_info(self):
        return {}


def pages_from_har(har: dict) -> dict[str, str]:
    return {
        e["request"]["url"].split("?")[0]: e["response"]["content"].get("text", "")
        for e in har["log"]["entries"]
        if "www.hygng.com" in e["request"]["url"]
    }


def main(har_path: str) -> int:
    har = json.loads(Path(har_path).read_text(encoding="utf-8"))
    pages = pages_from_har(har)

    index = next(v for k, v in pages.items() if k.endswith("/WXInquireFee/index1"))
    accounts = parse_accounts(index)
    assert accounts, "no account parsed"
    bills = parse_bills(next(v for k, v in pages.items() if "InquireFeeRecord1" in k))
    assert len(bills) == 12, len(bills)

    data = HygngData(account=accounts[0], bills=bills)
    coord = FakeCoordinator(data)

    entity = HygngBillHistorySensor.__new__(HygngBillHistorySensor)
    entity.coordinator = coord

    assert entity.native_value == 12, entity.native_value
    attrs = entity.extra_state_attributes
    assert attrs is not None
    assert attrs["count"] == 12
    assert attrs["newest_month"] == "2026-10"
    assert attrs["oldest_month"] == "2025-11"
    assert len(attrs["bills"]) == 12

    newest = attrs["bills"][0]
    expected_keys = {
        "read_id",
        "fee_month",
        "period_start",
        "period_end",
        "amount",
        "usage",
        "daily_average",
        "qty_day",
        "price",
        "before_qty",
        "current_qty",
        "penalty",
        "ladder_amount",
        "sum_amount",
        "year_amount",
        "read_type",
        "status",
        "title",
        "meter_number",
        "name",
        "address",
        "is_paid",
    }
    missing = expected_keys - set(newest)
    assert not missing, missing
    assert newest["fee_month"] == "2026-10"
    assert newest["amount"] == 23.1
    assert newest["usage"] == 6.0
    assert newest["is_paid"] is True

    print("history:", entity.native_value, "期，合计", attrs["total_amount"], "元，")
    print("总用气量", attrs["total_usage"], "m3，未缴月份", attrs["unpaid_months"])
    for row in attrs["bills"][:4]:
        print(f"  {row['fee_month']}: {row['amount']} 元 / {row['usage']} m3 / {row['status']}")
    print("\nSENSOR SHAPES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
