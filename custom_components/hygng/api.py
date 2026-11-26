"""Async client for the 惠州光能燃气 (www.hygng.com) WeChat portal.

Authentication is a single ASP.NET session cookie. Everything else (openid,
customer ids, meter numbers) is derived from the bill query page, so the user
only ever has to paste the cookie captured from 微信 / 浏览器.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_BILLS,
    ENDPOINT_BILL_DETAIL,
    ENDPOINT_INDEX,
    ENDPOINT_LADDER,
    ENDPOINT_USAGE,
    USER_AGENT,
)
from .parser import (
    BILL_DETAIL_PARAMS,
    Account,
    Bill,
    parse_accounts,
    parse_bill_detail,
    parse_bills,
    parse_focus_customer_id,
    parse_ladder,
    parse_openid,
    parse_usage,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)


class HygngError(Exception):
    """Base error for this integration."""


class HygngAuthError(HygngError):
    """The ASP.NET session cookie is missing, expired or invalid."""


class HygngConnectionError(HygngError):
    """The portal could not be reached or timed out."""


def normalise_cookie(value: str) -> str:
    """Accept a full cookie header or a bare ASP.NET session id."""
    cookie = (value or "").strip()
    if not cookie:
        return ""
    # Strip a leading "Cookie:" copied from devtools, and newlines from a long paste.
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    cookie = " ".join(cookie.split())
    if "=" not in cookie:
        return f"ASP.NET_SessionId={cookie}"
    return cookie


class HygngApi:
    """Thin client around the portal's rendered-HTML endpoints."""

    def __init__(self, session: aiohttp.ClientSession, cookie: str) -> None:
        self._session = session
        self._cookie = normalise_cookie(cookie)

    @property
    def cookie(self) -> str:
        """The cookie header currently in use."""
        return self._cookie

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer or f"{BASE_URL}/",
            "Cookie": self._cookie,
        }

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> str:
        headers = self._headers(referer)
        if data is not None:
            headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": BASE_URL,
                    "X-Requested-With": "XMLHttpRequest",
                }
            )
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location", "")
                    _LOGGER.debug("Portal redirected to %s", location)
                    raise HygngAuthError("session cookie rejected by portal")
                if response.status != 200:
                    raise HygngError(f"HTTP {response.status} for {url}")
                text = await response.text(errors="replace")
        except aiohttp.ClientError as err:
            raise HygngConnectionError(str(err)) from err
        except asyncio.TimeoutError as err:
            raise HygngConnectionError("timeout talking to hygng.com") from err

        if "系统出错" in text or "/Error/Index" in text:
            raise HygngAuthError("portal reported an error, cookie likely expired")
        return text

    async def async_get_accounts(self) -> tuple[list[Account], str]:
        """Return the accounts bound to the session plus the openid."""
        page = await self._request(f"{ENDPOINT_INDEX}?customerId=")
        accounts = parse_accounts(page)
        if not accounts:
            raise HygngAuthError("no account found for this cookie")
        return accounts, parse_openid(page)

    async def async_get_focus_customer_id(self) -> str:
        """Return the account the portal is focused on (may be empty)."""
        page = await self._request(f"{ENDPOINT_INDEX}?customerId=")
        return parse_focus_customer_id(page)

    async def async_get_bills(self, customer_id: str, openid: str) -> list[Bill]:
        """Return every bill the portal lists (usually the last 12 months)."""
        page = await self._request(
            ENDPOINT_BILLS,
            method="POST",
            data={"FCustomerId": customer_id, "openid": openid},
            referer=f"{ENDPOINT_INDEX}?customerId={customer_id}",
        )
        bills = parse_bills(page)
        _LOGGER.debug("portal returned %s bills for %s", len(bills), customer_id)
        return bills

    def _bill_detail_url(self, bill: Bill, customer_id: str, openid: str) -> str:
        params: dict[str, str] = {}
        for param, key in BILL_DETAIL_PARAMS.items():
            params[param] = bill.get(key)
        params["OpenId"] = openid
        params["FCustomerId"] = customer_id
        params["GuestID"] = customer_id
        return f"{ENDPOINT_BILL_DETAIL}?{urlencode(params)}"

    async def async_get_bill_detail(
        self, bill: Bill, customer_id: str, openid: str
    ) -> dict[str, Any]:
        """Return the itemised bill (抄表读数、单价、违约金、阶梯、合计应缴)."""
        page = await self._request(
            self._bill_detail_url(bill, customer_id, openid),
            referer=f"{ENDPOINT_INDEX}?customerId={customer_id}",
        )
        detail = parse_bill_detail(page)
        if not detail.get("fee_month"):
            detail["fee_month"] = bill.fee_month
        if not detail.get("read_id"):
            detail["read_id"] = bill.read_id
        detail["status"] = bill.status
        return detail

    async def async_get_usage(
        self, bill: Bill, customer_id: str, openid: str
    ) -> dict[str, Any]:
        """Return the 用气管理 page: summary cards plus the 6 month bar chart."""
        params = {
            "openid": openid,
            "meterNumberMe": bill.get("meter_number"),
            "customerId": customer_id,
            "name": bill.get("name"),
            "address": bill.get("address"),
            "amount": bill.get("amount"),
            "actualQty": bill.get("actual_qty"),
            "readDatePer": bill.get("read_date_prev"),
            "readDate": bill.get("read_date"),
            "mouth": bill.fee_month,
            "currentDateStr": bill.get("bill_title"),
            "qtyDay": bill.get("qty_day"),
            "FSumAmount": bill.get("sum_amount"),
        }
        page = await self._request(
            f"{ENDPOINT_USAGE}?{urlencode(params)}",
            referer=f"{ENDPOINT_INDEX}?customerId={customer_id}",
        )
        return parse_usage(page)

    async def async_get_ladder(self, read_id: str) -> dict[str, Any]:
        """Return the tier explanation page for a bill."""
        page = await self._request(
            f"{ENDPOINT_LADDER}?FReadId={read_id}",
            referer=f"{ENDPOINT_INDEX}",
        )
        return parse_ladder(page)
