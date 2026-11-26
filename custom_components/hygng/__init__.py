"""The 惠州光能燃气 (www.hygng.com) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HygngApi, HygngAuthError
from .const import CONF_COOKIE, CONF_CUSTOMER_ID, DOMAIN
from .coordinator import HygngCoordinator
from .parser import Account
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


@dataclass
class HygngRuntimeData:
    """Objects kept alive for the lifetime of a config entry."""

    api: HygngApi
    coordinator: HygngCoordinator
    session: aiohttp.ClientSession
    account: Account


type HygngConfigEntry = ConfigEntry[HygngRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (no YAML configuration supported)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HygngConfigEntry) -> bool:
    """Set up 惠州光能燃气 from a config entry."""
    cookie = entry.data[CONF_COOKIE]
    customer_id = entry.data[CONF_CUSTOMER_ID]

    # A dedicated session with a dummy cookie jar: the portal is driven purely by
    # the Cookie header and must never inherit or leak cookies from other entries.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    api = HygngApi(session, cookie)

    try:
        accounts, openid = await api.async_get_accounts()
    except HygngAuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception:
        await session.close()
        raise

    if not accounts:
        await session.close()
        raise ConfigEntryAuthFailed("未获取到任何户号，Cookie 可能已失效")

    account = next((a for a in accounts if a.customer_id == customer_id), None)
    if account is None:
        _LOGGER.warning(
            "户号 %s 已不在账号列表中，改用 %s", customer_id, accounts[0].customer_id
        )
        account = accounts[0]

    coordinator = HygngCoordinator(
        hass, entry, api, account.customer_id, account, openid
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = HygngRuntimeData(
        api=api, coordinator=coordinator, session=session, account=account
    )
    # The session is created inside config entry setup, so Home Assistant closes
    # it automatically on unload (auto_cleanup default).

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HygngConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        still_loaded = [
            item
            for item in hass.config_entries.async_entries(DOMAIN)
            if item.state is ConfigEntryState.LOADED
        ]
        if not still_loaded:
            await async_unload_services(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: HygngConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
