"""Offline parser regression test driven by the captured HAR file.

    python tests/test_parsers.py "C:\\path\\to\\www.hygng.com_....har"

Importing ``custom_components.hygng.parser`` as a package would execute the
Home Assistant dependent ``__init__``, so the module is loaded by file path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARSER_PATH = ROOT / "custom_components" / "hygng" / "parser.py"

spec = importlib.util.spec_from_file_location("hygng_parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["hygng_parser"] = parser
spec.loader.exec_module(parser)


def load_har(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as handle:
        har = json.load(handle)
    out: dict[str, str] = {}
    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        text = entry["response"]["content"].get("text", "")
        if not text or len(text) < len(out.get(url, "")):
            continue
        out[url] = text
    return out


def main() -> int:
    har_path = sys.argv[1]
    pages = load_har(har_path)

    index = next(v for k, v in pages.items() if "/WXInquireFee/index1" in k)
    bills_page = next(v for k, v in pages.items() if "InquireFeeRecord1" in k)

    accounts = parser.parse_accounts(index)
    print("accounts:", accounts)
    assert accounts and accounts[0].customer_id == "148358"
    assert accounts[0].name == "雷小军"

    openid = parser.parse_openid(index)
    print("openid:", openid)
    assert openid.startswith("oo3")

    bills = parser.parse_bills(bills_page)
    print("bills:", len(bills))
    assert len(bills) == 12
    assert bills[0].fee_month == "2026-10"
    assert bills[0].amount == 23.1
    assert bills[0].usage == 6.0
    assert bills[0].daily_average == 0.2
    assert bills[0].is_paid
    assert bills[0].read_id == "18231110"

    detail_page = next(v for k, v in pages.items() if "/WXGasFeeOpen/Index1" in k)
    detail = parser.parse_bill_detail(detail_page)
    print("detail:", detail)
    assert detail["name"] == "雷小军"
    assert detail["current_qty"] == 306.0
    assert detail["price"] == 3.85
    assert detail["amount"] == 23.1
    assert detail["penalty"] == 0.0
    assert detail["ladder_amount"] == 0.0
    assert detail["sum_amount"] == 0.005
    assert detail["read_type"] == "Y遥读"

    usage_page = next(v for k, v in pages.items() if "FeeManage" in k)
    usage = parser.parse_usage(usage_page)
    print("usage:", usage)
    assert usage["amount"] == 23.1
    assert usage["usage"] == 6.0
    assert usage["daily_average"] == 0.2
    assert len(usage["chart"]) == 6
    assert usage["chart"][-1]["month"] == "2026-10"

    ladder_page = next(v for k, v in pages.items() if "ladderDetail" in k)
    ladder = parser.parse_ladder(ladder_page)
    print("ladder:", ladder["tiers"])
    assert [t["tier"] for t in ladder["tiers"]] == [1, 2, 3]
    assert ladder["tiers"][0]["end"] == 366.0
    assert ladder["tiers"][1]["price"] == 4.24
    assert ladder["tiers"][2]["end"] is None
    assert parser.tier_for_usage(154, ladder["tiers"]) == 1
    assert parser.tier_for_usage(400, ladder["tiers"]) == 2
    assert parser.tier_for_usage(600, ladder["tiers"]) == 3

    print("\nALL PARSER CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
