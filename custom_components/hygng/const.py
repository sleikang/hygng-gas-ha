"""Constants for the 惠州光能燃气 (Huizhou Guangneng Gas) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hygng"

BASE_URL: Final = "https://www.hygng.com"

# WeChat-browser style UA. The portal gates several endpoints on this UA.
USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 NetType/WIFI "
    "MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf254210a) XWEB/26308 Flue"
)

ENDPOINT_INDEX: Final = f"{BASE_URL}/WXInquireFee/index1"
ENDPOINT_BILLS: Final = f"{BASE_URL}/WXInquireFee/InquireFeeRecord1"
ENDPOINT_BILL_DETAIL: Final = f"{BASE_URL}/WXGasFeeOpen/Index1"
ENDPOINT_USAGE: Final = f"{BASE_URL}/WXInquireFee/FeeManage"
ENDPOINT_LADDER: Final = f"{BASE_URL}/WXGasFeeOpen/ladderDetail"

CONF_COOKIE: Final = "cookie"
CONF_CUSTOMER_ID: Final = "customer_id"
CONF_ACCOUNT_NAME: Final = "account_name"
CONF_ACCOUNT_ADDRESS: Final = "account_address"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_HOURS: Final = 6
MIN_SCAN_INTERVAL_HOURS: Final = 1
MAX_SCAN_INTERVAL_HOURS: Final = 24

DEFAULT_NAME: Final = "惠州光能燃气"

MANUFACTURER: Final = "惠阳光能管道燃气"

# Resale tier thresholds published by 惠阳发改价【2019】28号文 (see ladderDetail page).
DEFAULT_TIERS: Final[tuple[dict[str, float | int | str], ...]] = (
    {"tier": 1, "start": 0.0, "end": 366.0, "price": 3.85},
    {"tier": 2, "start": 366.0, "end": 540.0, "price": 4.24},
    {"tier": 3, "start": 540.0, "end": None, "price": 5.01},
)
