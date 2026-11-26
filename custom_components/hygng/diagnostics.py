"""Diagnostics support for the 惠州光能燃气 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import HygngConfigEntry
from .const import CONF_COOKIE


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HygngConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the session cookie redacted."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    data = coordinator.data

    cookie = entry.data.get(CONF_COOKIE, "")
    parts = []
    for chunk in cookie.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            parts.append(f"{key}=**REDACTED**({len(value)}字符)")
        else:
            parts.append("**REDACTED**")

    return {
        "entry": {
            "title": entry.title,
            "data": {
                "cookie": "; ".join(parts),
                "customer_id": entry.data.get("customer_id"),
                "account_name": entry.data.get("account_name"),
                "account_address": entry.data.get("account_address"),
            },
            "options": dict(entry.options),
        },
        "account": {
            "customer_id": runtime.account.customer_id,
            "name": runtime.account.name,
            "address": runtime.account.address,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "bills": len(data.bills) if data else 0,
        },
        "data": data.summary() if data else None,
        "usage_chart": data.usage.get("chart") if data else None,
        "ladder": data.ladder if data else None,
    }
