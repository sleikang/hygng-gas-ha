"""Config flow for the 惠州光能燃气 integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HygngApi, HygngAuthError, HygngConnectionError
from .const import (
    CONF_ACCOUNT_ADDRESS,
    CONF_ACCOUNT_NAME,
    CONF_COOKIE,
    CONF_CUSTOMER_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)
from .parser import Account

_LOGGER = logging.getLogger(__name__)

COOKIE_HELP = (
    "在微信中打开「惠阳光能管道燃气」账单页面，用抓包工具（如 Stream / Charles / "
    "浏览器开发者工具）复制请求头里的 Cookie，形如 ASP.NET_SessionId=xxxxxxxx。"
)


async def _async_fetch_accounts(
    hass, cookie: str
) -> tuple[list[Account], str]:
    """Validate a cookie and return the bound accounts."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    api = HygngApi(session, cookie)
    try:
        return await api.async_get_accounts()
    finally:
        await session.close()


class HygngConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._cookie: str = ""
        self._accounts: list[Account] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the session cookie."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            try:
                accounts, _openid = await _async_fetch_accounts(self.hass, cookie)
            except HygngAuthError:
                errors["base"] = "invalid_auth"
            except HygngConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface as generic error
                _LOGGER.exception("unexpected error validating cookie")
                errors["base"] = "unknown"
            else:
                if not accounts:
                    errors["base"] = "no_accounts"
                else:
                    self._cookie = cookie
                    self._accounts = accounts
                    if len(accounts) == 1:
                        return await self._async_create_entry(accounts[0])
                    return await self.async_step_account()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COOKIE): TextSelector(
                        TextSelectorConfig(
                            multiline=True,
                            type=TextSelectorType.TEXT,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"cookie_help": COOKIE_HELP},
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which 户号 to track when the cookie has several."""
        if user_input is not None:
            account = next(
                a for a in self._accounts if a.customer_id == user_input[CONF_CUSTOMER_ID]
            )
            return await self._async_create_entry(account)

        options = [
            SelectOptionDict(
                value=account.customer_id,
                label=f"{account.name}（{account.address}）" if account.address else account.name,
            )
            for account in self._accounts
        ]
        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CUSTOMER_ID): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _async_create_entry(self, account: Account) -> ConfigFlowResult:
        await self.async_set_unique_id(account.customer_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"{DEFAULT_NAME} {account.label}",
            data={
                CONF_COOKIE: self._cookie,
                CONF_CUSTOMER_ID: account.customer_id,
                CONF_ACCOUNT_NAME: account.name,
                CONF_ACCOUNT_ADDRESS: account.address,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start the re-authentication flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh cookie after the session expired."""
        errors: dict[str, str] = {}

        if user_input is not None and self._reauth_entry is not None:
            cookie = user_input[CONF_COOKIE].strip()
            try:
                accounts, _openid = await _async_fetch_accounts(self.hass, cookie)
            except HygngAuthError:
                errors["base"] = "invalid_auth"
            except HygngConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("unexpected error during reauth")
                errors["base"] = "unknown"
            else:
                current = self._reauth_entry.data[CONF_CUSTOMER_ID]
                account = next(
                    (a for a in accounts if a.customer_id == current),
                    accounts[0] if accounts else None,
                )
                if account is None:
                    errors["base"] = "no_accounts"
                else:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data={
                            **self._reauth_entry.data,
                            CONF_COOKIE: cookie,
                            CONF_CUSTOMER_ID: account.customer_id,
                            CONF_ACCOUNT_NAME: account.name,
                            CONF_ACCOUNT_ADDRESS: account.address,
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COOKIE): TextSelector(
                        TextSelectorConfig(
                            multiline=True,
                            type=TextSelectorType.TEXT,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"cookie_help": COOKIE_HELP},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HygngOptionsFlow()


class HygngOptionsFlow(OptionsFlow):
    """Replace the cookie and tune the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            if cookie != entry.data[CONF_COOKIE]:
                try:
                    await _async_fetch_accounts(self.hass, cookie)
                except HygngAuthError:
                    errors["base"] = "invalid_auth"
                except HygngConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("unexpected error validating cookie")
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_COOKIE: cookie},
                    )
            if not errors:
                return self.async_create_entry(
                    data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]}
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COOKIE, default=entry.data[CONF_COOKIE]
                    ): TextSelector(
                        TextSelectorConfig(
                            multiline=True,
                            type=TextSelectorType.TEXT,
                        )
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_HOURS,
                            max=MAX_SCAN_INTERVAL_HOURS,
                            step=1,
                            unit_of_measurement="小时",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"cookie_help": COOKIE_HELP},
        )
