"""Smoke-test the config flow control logic without a full HA instance.

It monkeypatches the few Home Assistant helpers the flow touches, then walks the
real ``async_step_user`` / ``async_step_account`` code against the live portal.

Usage: python tests/flow_smoke.py "ASP.NET_SessionId=xxxxxxxx"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.hygng import config_flow as cfg  # noqa: E402


class FakeFlow:
    """Records what the flow would hand back to Home Assistant."""

    def __init__(self, flow: cfg.HygngConfigFlow) -> None:
        self.flow = flow
        self.unique_id: str | None = None
        self.entry: dict[str, Any] | None = None
        self.forms: list[tuple[str, dict[str, Any]]] = []

    def attach(self) -> None:
        flow = self.flow
        flow.hass = None  # type: ignore[assignment]

        async def async_set_unique_id(value: str, **_: Any) -> None:
            self.unique_id = value

        def _abort_if_unique_id_configured(**_: Any) -> None:
            return None

        def async_create_entry(**kwargs: Any) -> dict[str, Any]:
            self.entry = kwargs
            return {"type": "create_entry", **kwargs}

        def async_show_form(**kwargs: Any) -> dict[str, Any]:
            self.forms.append((kwargs["step_id"], kwargs.get("errors") or {}))
            return {"type": "form", **kwargs}

        flow.async_set_unique_id = async_set_unique_id  # type: ignore[method-assign]
        flow._abort_if_unique_id_configured = _abort_if_unique_id_configured  # type: ignore[method-assign]
        flow.async_create_entry = async_create_entry  # type: ignore[method-assign]
        flow.async_show_form = async_show_form  # type: ignore[method-assign]

    async def step_user(self, cookie: str) -> dict[str, Any]:
        return await self.flow.async_step_user({cfg.CONF_COOKIE: cookie})

    async def step_account(self, customer_id: str) -> dict[str, Any]:
        return await self.flow.async_step_account({cfg.CONF_CUSTOMER_ID: customer_id})


async def main(cookie: str) -> int:
    def _patched_session(hass, **kwargs):
        return aiohttp.ClientSession(**kwargs)

    original = cfg.async_create_clientsession
    cfg.async_create_clientsession = _patched_session  # type: ignore[assignment]
    try:
        # --- invalid cookie must surface as a form error -------------------
        flow = cfg.HygngConfigFlow()
        recorder = FakeFlow(flow)
        recorder.attach()
        result = await recorder.step_user("ASP.NET_SessionId=definitely-not-valid")
        assert result["type"] == "form", result
        assert result.get("errors", {}).get("base") == "invalid_auth", result
        print("invalid cookie ->", result.get("errors"))

        # --- valid cookie creates a single-account entry --------------------
        flow = cfg.HygngConfigFlow()
        recorder = FakeFlow(flow)
        recorder.attach()
        result = await recorder.step_user(cookie)
        assert result["type"] == "create_entry", result
        assert recorder.entry is not None
        data = recorder.entry["data"]
        assert data[cfg.CONF_COOKIE], data
        assert data[cfg.CONF_CUSTOMER_ID], data
        assert recorder.unique_id == data[cfg.CONF_CUSTOMER_ID]
        print("entry title:", recorder.entry["title"])
        print("entry data keys:", sorted(data))
    finally:
        cfg.async_create_clientsession = original  # type: ignore[assignment]

    print("\nCONFIG FLOW SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1])))
