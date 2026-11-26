"""Data update coordinator for the 惠州光能燃气 integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import HygngApi, HygngAuthError, HygngConnectionError, HygngError
from .const import (
    BASE_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_TIERS,
    DOMAIN,
    MANUFACTURER,
)
from .parser import Account, Bill, tier_for_usage

_LOGGER = logging.getLogger(__name__)


@dataclass
class HygngData:
    """Everything known about one 户号 after a poll."""

    account: Account
    bills: list[Bill] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    ladder: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    @property
    def latest(self) -> Bill | None:
        """Most recent bill."""
        return self.bills[0] if self.bills else None

    @property
    def tiers(self) -> list[dict[str, Any]]:
        """Tier table, falling back to the published tariff."""
        tiers = self.ladder.get("tiers") if self.ladder else None
        return list(tiers) if tiers else [dict(t) for t in DEFAULT_TIERS]

    @property
    def year_usage(self) -> float | None:
        """Year-to-date consumption, used for the tier calculation."""
        latest = self.latest
        if latest is None or latest.meter_reading is None:
            return None
        year = latest.fee_month[:4]
        same_year = [b for b in self.bills if b.fee_month.startswith(year)]
        starts = [b.previous_reading for b in same_year if b.previous_reading is not None]
        if not starts:
            return None
        return round(latest.meter_reading - min(starts), 3)

    @property
    def year_amount(self) -> float | None:
        """Year-to-date billed amount."""
        latest = self.latest
        if latest is None:
            return None
        reported = latest.num("year_amount")
        if reported:
            return round(reported, 2)
        year = latest.fee_month[:4]
        amounts = [b.amount for b in self.bills if b.fee_month.startswith(year)]
        total = [a for a in amounts if a is not None]
        return round(sum(total), 2) if total else None

    @property
    def current_tier(self) -> int | None:
        """Current tier for the year-to-date volume."""
        return tier_for_usage(self.year_usage, self.tiers)

    @property
    def unpaid(self) -> bool:
        """Whether the newest bill is still open."""
        latest = self.latest
        return bool(latest and not latest.is_paid)

    def bill_for_month(self, fee_month: str | None) -> Bill | None:
        """Return a bill by ``YYYY-MM`` (latest when omitted)."""
        if not fee_month:
            return self.latest
        for bill in self.bills:
            if bill.fee_month == fee_month:
                return bill
        return None

    def summary(self) -> dict[str, Any]:
        """Condensed state used by entities and services."""
        latest = self.latest
        if latest is None:
            return {}
        return {
            "customer_id": self.account.customer_id,
            "name": self.account.name,
            "address": self.account.address,
            "meter_number": latest.get("meter_number"),
            "fee_month": latest.fee_month,
            "bill_title": latest.get("bill_title"),
            "period_start": latest.period_start,
            "period_end": latest.period_end,
            "amount": latest.amount,
            "usage": latest.usage,
            "daily_average": latest.daily_average,
            "qty_day": latest.qty_day,
            "price": latest.price,
            "before_qty": latest.previous_reading,
            "current_qty": latest.meter_reading,
            "penalty": latest.num("penalty_amount"),
            "ladder_amount": latest.num("ladder_amount"),
            "sum_amount": latest.num("sum_amount"),
            "read_type": latest.get("read_type"),
            "status": latest.status,
            "year_usage": self.year_usage,
            "year_amount": self.year_amount,
            "tier": self.current_tier,
            "tiers": self.tiers,
            "bills": [b.as_dict() for b in self.bills],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class HygngCoordinator(DataUpdateCoordinator[HygngData]):
    """Polls the portal and caches the richer per-bill pages."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: HygngApi,
        customer_id: str,
        account: Account,
        openid: str = "",
    ) -> None:
        hours = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {customer_id}",
            update_interval=timedelta(hours=hours),
        )
        self.api = api
        self.customer_id = customer_id
        self.account = account
        self.openid = openid
        self._detail_cache: tuple[str, dict[str, Any]] | None = None
        self._usage_cache: tuple[str, dict[str, Any]] | None = None
        self._ladder_cache: tuple[str, dict[str, Any]] | None = None
        self._force_detail = False

    def request_full_refresh(self) -> None:
        """Make the next poll re-read the itemised pages."""
        self._force_detail = True

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry shared by every entity of this account."""
        meter = ""
        if self.data and self.data.latest:
            meter = self.data.latest.get("meter_number")
        return DeviceInfo(
            identifiers={(DOMAIN, self.customer_id)},
            name=f"{DEFAULT_NAME} {self.account.label}",
            manufacturer=MANUFACTURER,
            model=f"管道燃气表 {meter}".strip() if meter else "管道燃气",
            serial_number=meter or self.customer_id,
            configuration_url=BASE_URL,
        )

    async def _resolve_openid(self) -> str:
        if self.openid:
            return self.openid
        accounts, openid = await self.api.async_get_accounts()
        for account in accounts:
            if account.customer_id == self.customer_id:
                self.account = account
                break
        else:
            raise UpdateFailed(
                f"account {self.customer_id} is no longer bound to this cookie"
            )
        self.openid = openid
        return openid

    async def _async_update_data(self) -> HygngData:
        try:
            openid = await self._resolve_openid()
            bills = await self.api.async_get_bills(self.customer_id, openid)
            if not bills:
                raise UpdateFailed("portal returned no bills")

            data = HygngData(account=self.account, bills=bills)
            latest = bills[0]

            if self._force_detail or self._detail_cache is None or (
                self._detail_cache[0] != latest.read_id
            ):
                data.detail = await self.api.async_get_bill_detail(
                    latest, self.customer_id, openid
                )
                self._detail_cache = (latest.read_id, data.detail)
            else:
                data.detail = self._detail_cache[1]

            year = latest.fee_month[:4]
            if (
                self._force_detail
                or self._ladder_cache is None
                or self._ladder_cache[0] != year
            ):
                data.ladder = await self.api.async_get_ladder(latest.read_id)
                self._ladder_cache = (year, data.ladder)
            else:
                data.ladder = self._ladder_cache[1]

            if self._force_detail or self._usage_cache is None or (
                self._usage_cache[0] != latest.read_id
            ):
                data.usage = await self.api.async_get_usage(
                    latest, self.customer_id, openid
                )
                self._usage_cache = (latest.read_id, data.usage)
            else:
                data.usage = self._usage_cache[1]
            self._force_detail = False

            data.updated_at = dt_util.utcnow()
            return data

        except HygngAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HygngConnectionError as err:
            raise UpdateFailed(f"cannot reach hygng.com: {err}") from err
        except HygngError as err:
            raise UpdateFailed(str(err)) from err

    async def async_get_bill_detail(self, fee_month: str | None) -> dict[str, Any]:
        """Fetch the itemised bill for a given month (on demand)."""
        bill = (self.data.bill_for_month(fee_month) if self.data else None)
        if bill is None:
            raise UpdateFailed(f"no bill for month {fee_month}")
        if self.data and bill.read_id == self.data.latest.read_id and self.data.detail:
            return self.data.detail
        openid = await self._resolve_openid()
        return await self.api.async_get_bill_detail(bill, self.customer_id, openid)

    async def async_get_usage(self, fee_month: str | None) -> dict[str, Any]:
        """Fetch the 用气管理 page for a given month (on demand)."""
        bill = (self.data.bill_for_month(fee_month) if self.data else None)
        if bill is None:
            raise UpdateFailed(f"no bill for month {fee_month}")
        if (
            self.data
            and bill.read_id == self.data.latest.read_id
            and self.data.usage
        ):
            return self.data.usage
        openid = await self._resolve_openid()
        return await self.api.async_get_usage(bill, self.customer_id, openid)

    async def async_get_ladder(self, fee_month: str | None) -> dict[str, Any]:
        """Fetch the tier explanation page for a given month."""
        bill = (self.data.bill_for_month(fee_month) if self.data else None)
        if bill is None:
            raise UpdateFailed(f"no bill for month {fee_month}")
        return await self.api.async_get_ladder(bill.read_id)


class CoordinatorEntityBase(CoordinatorEntity[HygngCoordinator]):
    """Base entity that keeps the device info in sync."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HygngCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
