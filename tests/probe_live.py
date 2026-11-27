"""Dev-only probe: validates the HTML parsers against the live hygng.com portal.

Usage:
    python tests/probe_live.py "ASP.NET_SessionId=xxxxx"
"""

from __future__ import annotations

import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.hygng.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 NetType/WIFI "
    "MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf254210a) XWEB/26308 Flue"
)


def get(url: str, cookie: str, data: dict | None = None) -> str:
    body = None
    headers = {
        "User-Agent": UA,
        "Cookie": cookie,
        "Referer": f"{BASE}/",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Origin"] = BASE
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_accounts(html: str) -> list[dict]:
    out = []
    for m in re.finditer(
        r'<input[^>]+name="userOption"[^>]*>', html
    ):
        tag = m.group(0)
        val = re.search(r'value="([^"]*)"', tag)
        name = re.search(r'data-name="([^"]*)"', tag)
        addr = re.search(r'data-address="([^"]*)"', tag)
        out.append(
            {
                "customer_id": val.group(1) if val else "",
                "name": name.group(1) if name else "",
                "address": addr.group(1) if addr else "",
            }
        )
    if not out:
        for m in re.finditer(r"<option[^>]+>", html):
            tag = m.group(0)
            val = re.search(r'value="([^"]*)"', tag)
            name = re.search(r'data-name="([^"]*)"', tag)
            addr = re.search(r'data-address="([^"]*)"', tag)
            out.append(
                {
                    "customer_id": val.group(1) if val else "",
                    "name": name.group(1) if name else "",
                    "address": addr.group(1) if addr else "",
                }
            )
    return out


BILL_ARGS = [
    "meter_number",
    "read_date_prev",
    "name",
    "address",
    "read_date",
    "before_qty",
    "current_qty",
    "actual_qty",
    "price",
    "amount",
    "penalty_amount",
    "sum_amount",
    "ladder_amount",
    "tail_prev",
    "read_id",
    "fee_month",
    "customer_id",
    "gas_sum",
    "read_type",
    "penalty_prev",
    "qty_day",
    "amount_prev",
    "read_type_prev",
    "status",
    "bill_title",
]


def parse_bills(html: str) -> list[dict]:
    bills = []
    for m in re.finditer(r"BtnOpen\((.*?)\)\"", html):
        raw = m.group(1)
        args = [a.strip().strip("'") for a in raw.split(",")]
        if len(args) < len(BILL_ARGS):
            continue
        bill = dict(zip(BILL_ARGS, args))
        bills.append(bill)
    return bills


def parse_detail(html: str) -> dict:
    fields = {}
    for m in re.finditer(r"<h5>(.*?)</h5>", html, re.S):
        block = m.group(1)
        text = re.sub(r"<[^>]+>", "", block)
        text = text.replace("&nbsp;", " ").strip()
        if ":" not in text and "：" not in text:
            continue
        pairs = re.split(r"[:：]", text, maxsplit=1)
        fields[pairs[0].strip()] = pairs[1].strip() if len(pairs) > 1 else ""
    return fields


def main() -> None:
    cookie = sys.argv[1]
    html = get(f"{BASE}/WXInquireFee/index1?customerId=", cookie)
    print("index1 len", len(html))
    print("accounts", parse_accounts(html))
    m = re.search(r'"openid":\s*"([^"]+)"', html)
    openid = m.group(1) if m else ""
    print("openid", openid)
    accounts = parse_accounts(html)
    cid = accounts[0]["customer_id"] if accounts else ""

    bills_html = get(
        f"{BASE}/WXInquireFee/InquireFeeRecord1", cookie,
        {"FCustomerId": cid, "openid": openid},
    )
    bills = parse_bills(bills_html)
    print("bills", len(bills))
    for b in bills[:3]:
        print(b)

    if bills:
        latest = bills[0]
        params = {
            "FMeterNumber": latest["meter_number"],
            "FReadDatePer": latest["read_date_prev"],
            "FName": latest["name"],
            "FAddress": latest["address"],
            "FReadDate": latest["read_date"],
            "FBeforeQty": latest["before_qty"],
            "FCurrentQty": latest["current_qty"],
            "FActualQty": latest["actual_qty"],
            "FPrice": latest["price"],
            "FAmount": latest["amount"],
            "FWYAmount": latest["penalty_amount"],
            "FSumAmount": latest["sum_amount"],
            "LadderAmount": latest["ladder_amount"],
            "FTailPre": latest["tail_prev"],
            "FReadId": latest["read_id"],
            "FFeeMonth": latest["fee_month"],
            "GuestID": latest["customer_id"],
            "FGasSum": latest["gas_sum"],
            "FMeterReadingType": latest["read_type"],
            "OpenId": openid,
            "FCustomerId": cid,
            "FWYAmountPre": latest["penalty_prev"],
            "FQtyDay": latest["qty_day"],
            "FAmountPre": latest["amount_prev"],
            "FMeterReadingTypePer": latest["read_type_prev"],
            "FStatus": latest["status"],
            "FCurrentDateStr": latest["bill_title"],
        }
        detail_url = f"{BASE}/WXGasFeeOpen/Index1?" + urllib.parse.urlencode(params)
        detail = parse_detail(get(detail_url, cookie))
        print("detail", len(detail))
        for k, v in detail.items():
            print("   ", k, "=", v)

        ladder = get(
            f"{BASE}/WXGasFeeOpen/ladderDetail?FReadId={latest['read_id']}", cookie
        )
        print("ladder len", len(ladder))
        txt = re.sub(r"<[^>]+>", " ", ladder)
        txt = re.sub(r"\s+", " ", txt).strip()
        print(txt[:400])


if __name__ == "__main__":
    main()
