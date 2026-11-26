"""Boot a real Home Assistant and exercise the integration end to end.

    python tests/ha_smoke.py "ASP.NET_SessionId=xxxx"

Requires a working Home Assistant install in the running interpreter.
Creates a throw-away config dir, installs the component, runs the config flow,
waits for the entities, then calls every service.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeassistant import bootstrap  # noqa: E402
from homeassistant.runner import RuntimeConfig  # noqa: E402

DOMAIN = "hygng"


async def run(cookie: str) -> int:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("homeassistant").setLevel(logging.WARNING)
    logging.getLogger("custom_components.hygng").setLevel(logging.DEBUG)

    config_dir = pathlib.Path(tempfile.mkdtemp(prefix="hygng-ha-"))
    (config_dir / "custom_components").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT / "custom_components" / DOMAIN,
        config_dir / "custom_components" / DOMAIN,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  time_zone: Asia/Shanghai\n", encoding="utf-8"
    )

    runtime = RuntimeConfig(
        config_dir=str(config_dir),
        skip_pip=True,
        skip_pip_packages=True,
        recovery_mode=False,
        verbose=False,
        log_rotate_days=None,
        log_file=None,
        log_no_color=True,
        debug=False,
        open_ui=False,
        safe_mode=False,
    )
    hass = await bootstrap.async_setup_hass(runtime)
    assert hass is not None, "hass failed to boot"

    try:
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        print("flow step:", flow["step_id"], "errors:", flow.get("errors"))
        assert flow["type"] == "form"

        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"cookie": cookie}
        )
        print("flow result:", result["type"], result.get("reason"))
        assert result["type"] == "create_entry", result

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        await hass.async_block_till_done()
        print("entry state:", entry.state)

        states = [
            state
            for state in hass.states.async_all()
            if str(state.attributes.get("friendly_name", "")).startswith("惠州光能燃气")
        ]
        print(f"entities: {len(states)}")
        for state in sorted(states, key=lambda item: item.entity_id):
            print(f"  {state.entity_id} = {state.state}")
        assert len(states) > 10, "entities were not created"

        for service in (
            "get_accounts",
            "get_bills",
            "get_bill_detail",
            "get_usage",
            "get_ladder_detail",
        ):
            response = await hass.services.async_call(
                DOMAIN, service, {}, blocking=True, return_response=True
            )
            first = response["results"][0]
            print(f"service {service} -> {sorted(first)[:8]}")

        await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
        print("service refresh -> ok")

        from custom_components.hygng.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        diag = await async_get_config_entry_diagnostics(hass, entry)
        cookie_out = diag["entry"]["data"]["cookie"]
        print("diagnostics cookie:", cookie_out)
        assert "REDACTED" in cookie_out
        assert "sejtctr" not in cookie_out

        print("\nHA SMOKE TEST PASSED")
        return 0
    finally:
        await hass.async_stop(force=True)
        shutil.rmtree(config_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(os.environ.get("HYGNG_COOKIE") or sys.argv[1])))
