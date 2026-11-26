"""Action handlers for the 惠州光能燃气 integration.

These mirror every page of the WeChat portal:

* ``get_accounts``      - 账单查询首页的户号列表
* ``get_bills``         - 账单列表（最近 12 个月）
* ``get_bill_detail``   - 账单明细（抄表、单价、违约金、阶梯、合计应缴）
* ``get_usage``         - 用气管理（本期汇总 + 近 6 个月日均用气）
* ``get_ladder_detail`` - 阶梯用气明细（档位与单价说明）
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import DOMAIN
from .coordinator import HygngCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_ACCOUNTS = "get_accounts"
SERVICE_GET_BILLS = "get_bills"
SERVICE_GET_BILL_DETAIL = "get_bill_detail"
SERVICE_GET_USAGE = "get_usage"
SERVICE_GET_LADDER = "get_ladder_detail"
SERVICE_REFRESH = "refresh"

SERVICES = (
    SERVICE_GET_ACCOUNTS,
    SERVICE_GET_BILLS,
    SERVICE_GET_BILL_DETAIL,
    SERVICE_GET_USAGE,
    SERVICE_GET_LADDER,
    SERVICE_REFRESH,
)

ENTRY_SCHEMA = {
    vol.Optional("entry_id"): selector.ConfigEntrySelector(
        selector.ConfigEntrySelectorConfig(integration=DOMAIN)
    ),
}

MONTH_SCHEMA = {
    vol.Optional("month"): cv.string,
}

LIMIT_SCHEMA = {
    vol.Optional("limit", default=12): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=36)
    ),
}


def _iter_coordinators(
    hass: HomeAssistant, entry_id: str | None
) -> list[tuple[str, HygngCoordinator]]:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    selected = [e for e in entries if entry_id is None or e.entry_id == entry_id]
    if not selected:
        raise ServiceValidationError("没有可用的惠州光能燃气配置项")
    out: list[tuple[str, HygngCoordinator]] = []
    for entry in selected:
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            continue
        out.append((entry.entry_id, runtime.coordinator))
    if not out:
        raise ServiceValidationError("配置项尚未完成初始化")
    return out


async def _async_handle_get_accounts(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    coordinators = _iter_coordinators(hass, call.data.get("entry_id"))
    results: list[dict[str, Any]] = []
    for _entry_id, coordinator in coordinators:
        try:
            accounts, openid = await coordinator.api.async_get_accounts()
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"查询户号失败：{err}") from err
        results.append(
            {
                "current_customer_id": coordinator.customer_id,
                "openid": openid,
                "accounts": [
                    {
                        "customer_id": a.customer_id,
                        "name": a.name,
                        "address": a.address,
                    }
                    for a in accounts
                ],
            }
        )
    return {"results": results}


async def _async_handle_get_bills(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    limit = call.data.get("limit", 12)
    results: list[dict[str, Any]] = []
    for _entry_id, coordinator in _iter_coordinators(hass, call.data.get("entry_id")):
        data = coordinator.data
        if data is None:
            raise HomeAssistantError("尚未获取到账单数据，请稍后重试")
        results.append(
            {
                "customer_id": data.account.customer_id,
                "name": data.account.name,
                "address": data.account.address,
                "count": len(data.bills),
                "bills": [bill.as_dict() for bill in data.bills[:limit]],
            }
        )
    return {"results": results}


async def _async_handle_get_bill_detail(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    month = call.data.get("month")
    results: list[dict[str, Any]] = []
    for _entry_id, coordinator in _iter_coordinators(hass, call.data.get("entry_id")):
        try:
            detail = await coordinator.async_get_bill_detail(month)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"获取账单明细失败：{err}") from err
        results.append(detail)
    return {"results": results}


async def _async_handle_get_usage(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    month = call.data.get("month")
    results: list[dict[str, Any]] = []
    for _entry_id, coordinator in _iter_coordinators(hass, call.data.get("entry_id")):
        try:
            usage = await coordinator.async_get_usage(month)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"获取用气管理数据失败：{err}") from err
        results.append(usage)
    return {"results": results}


async def _async_handle_get_ladder(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    month = call.data.get("month")
    results: list[dict[str, Any]] = []
    for _entry_id, coordinator in _iter_coordinators(hass, call.data.get("entry_id")):
        try:
            ladder = await coordinator.async_get_ladder(month)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"获取阶梯明细失败：{err}") from err
        data = coordinator.data
        results.append(
            {
                "tiers": ladder.get("tiers", []),
                "note": ladder.get("note", ""),
                "year_usage": data.year_usage if data else None,
                "current_tier": data.current_tier if data else None,
            }
        )
    return {"results": results}


async def _async_handle_refresh(call: ServiceCall) -> ServiceResponse:
    hass: HomeAssistant = call.hass
    results: list[dict[str, Any]] = []
    for entry_id, coordinator in _iter_coordinators(hass, call.data.get("entry_id")):
        coordinator.request_full_refresh()
        await coordinator.async_refresh()
        data = coordinator.data
        results.append(
            {
                "entry_id": entry_id,
                "success": coordinator.last_update_success,
                "fee_month": data.latest.fee_month if data and data.latest else None,
                "amount": data.latest.amount if data and data.latest else None,
            }
        )
    return {"results": results}


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the action handlers once."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_BILLS):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ACCOUNTS,
        _async_handle_get_accounts,
        schema=vol.Schema(ENTRY_SCHEMA),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_BILLS,
        _async_handle_get_bills,
        schema=vol.Schema({**ENTRY_SCHEMA, **LIMIT_SCHEMA}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_BILL_DETAIL,
        _async_handle_get_bill_detail,
        schema=vol.Schema({**ENTRY_SCHEMA, **MONTH_SCHEMA}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_USAGE,
        _async_handle_get_usage,
        schema=vol.Schema({**ENTRY_SCHEMA, **MONTH_SCHEMA}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LADDER,
        _async_handle_get_ladder,
        schema=vol.Schema({**ENTRY_SCHEMA, **MONTH_SCHEMA}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _async_handle_refresh,
        schema=vol.Schema(ENTRY_SCHEMA),
        supports_response=SupportsResponse.OPTIONAL,
    )
    _LOGGER.debug("services registered for %s", DOMAIN)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the handlers when the last entry goes away."""
    if hass.config_entries.async_loaded_entries(DOMAIN):
        return
    for service in SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
