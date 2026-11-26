"""End-to-end client check against the live portal.

    python tests/live_api_check.py "ASP.NET_SessionId=xxxx"

Exercises every endpoint the integration uses, with the same call shapes as
``coordinator.py``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.hygng.api import HygngApi  # noqa: E402
from custom_components.hygng.coordinator import HygngData  # noqa: E402


async def main(cookie: str) -> int:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        api = HygngApi(session, cookie)

        accounts, openid = await api.async_get_accounts()
        print(f"accounts={accounts} openid={openid[:8]}...")
        assert accounts, "no accounts parsed"

        customer_id = accounts[0].customer_id
        bills = await api.async_get_bills(customer_id, openid)
        print(f"bills={len(bills)} newest={bills[0].fee_month} {bills[0].amount}元")
        assert bills, "no bills parsed"

        latest = bills[0]
        detail = await api.async_get_bill_detail(latest, customer_id, openid)
        print(
            "detail:",
            {k: detail.get(k) for k in ("current_qty", "actual_qty", "price", "amount", "penalty", "sum_amount")},
            "status=",
            detail.get("status"),
        )
        assert detail.get("current_qty") is not None, "detail page did not parse"

        usage = await api.async_get_usage(latest, customer_id, openid)
        print("usage:", usage.get("fee_month"), usage.get("amount"), "chart points", len(usage.get("chart", [])))
        assert usage.get("chart"), "usage chart missing"

        ladder = await api.async_get_ladder(latest.read_id)
        print("ladder tiers:", ladder.get("tiers"))
        assert len(ladder.get("tiers", [])) >= 2, "ladder tiers missing"

        data = HygngData(account=accounts[0], bills=bills, detail=detail, usage=usage, ladder=ladder)
        print(
            "computed: year_usage=",
            data.year_usage,
            "year_amount=",
            data.year_amount,
            "tier=",
            data.current_tier,
            "unpaid=",
            data.unpaid,
        )
        assert data.year_usage and data.year_usage > 0
        assert data.current_tier in (1, 2, 3)

        summary = data.summary()
        print("summary keys:", sorted(summary)[:8], "...")
        print("\nLIVE API CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1])))
