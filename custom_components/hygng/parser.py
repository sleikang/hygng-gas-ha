"""HTML parsers for the 惠州光能燃气 WeChat portal.

The portal is an ASP.NET MVC mini-site: every "API" answers with a rendered
HTML fragment, so the parsers below are the actual data layer. They are kept
free of Home Assistant imports so they can be exercised standalone
(see ``tests/probe_live.py``).
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import Any

# Order of the arguments passed to the JS ``BtnOpen(...)`` handler on the bill
# list page. Value 25 is the bill title.
BILL_ARGS: tuple[str, ...] = (
    "meter_number",  # FMeterNumber
    "read_date_prev",  # FReadDatePer
    "name",  # FName
    "address",  # FAddress
    "read_date",  # FReadDate
    "before_qty",  # FBeforeQty
    "current_qty",  # FCurrentQty
    "actual_qty",  # FActualQty
    "price",  # FPrice
    "amount",  # FAmount
    "penalty_amount",  # FWYAmount
    "sum_amount",  # FSumAmount
    "ladder_amount",  # LadderAmount
    "tail_prev",  # FTailPre
    "read_id",  # FReadId
    "fee_month",  # FFeeMonth
    "customer_id",  # GuestID
    "gas_sum",  # FGasSum
    "read_type",  # FMeterReadingType
    "penalty_prev",  # FWYAmountPre
    "qty_day",  # FQtyDay
    "year_amount",  # FAmountPre  (year-to-date cumulative fee)
    "read_type_prev",  # FMeterReadingTypePer
    "status",  # FStatus
    "bill_title",  # FCurrentDateStr
)

BILL_DETAIL_PARAMS: dict[str, str] = {
    "FMeterNumber": "meter_number",
    "FReadDatePer": "read_date_prev",
    "FName": "name",
    "FAddress": "address",
    "FReadDate": "read_date",
    "FBeforeQty": "before_qty",
    "FCurrentQty": "current_qty",
    "FActualQty": "actual_qty",
    "FPrice": "price",
    "FAmount": "amount",
    "FWYAmount": "penalty_amount",
    "FSumAmount": "sum_amount",
    "LadderAmount": "ladder_amount",
    "FTailPre": "tail_prev",
    "FReadId": "read_id",
    "FFeeMonth": "fee_month",
    "GuestID": "customer_id",
    "FGasSum": "gas_sum",
    "FMeterReadingType": "read_type",
    "FWYAmountPre": "penalty_prev",
    "FQtyDay": "qty_day",
    "FAmountPre": "year_amount",
    "FMeterReadingTypePer": "read_type_prev",
    "FStatus": "status",
    "FCurrentDateStr": "bill_title",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def to_float(value: Any, default: float | None = None) -> float | None:
    """Return ``value`` as float, or ``default`` when it is not numeric."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clean_text(value: str) -> str:
    """Strip markup, entities and duplicated whitespace from an HTML snippet."""
    text = _TAG_RE.sub(" ", value)
    text = html_lib.unescape(text).replace("\xa0", " ")
    text = text.replace("&nbsp;", " ")
    return _WS_RE.sub(" ", text).strip()


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', tag)
    return html_lib.unescape(match.group(1)).strip() if match else ""


@dataclass
class Account:
    """One 户号 (customer account) bound to the session."""

    customer_id: str
    name: str = ""
    address: str = ""

    @property
    def label(self) -> str:
        """Human readable label, falling back to the customer id."""
        return self.name or self.customer_id


@dataclass
class Bill:
    """A monthly gas bill as rendered by ``InquireFeeRecord1``."""

    raw: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        """Return a raw string field."""
        return self.raw.get(key, default)

    def num(self, key: str, default: float | None = None) -> float | None:
        """Return a raw field as float."""
        return to_float(self.raw.get(key), default)

    @property
    def read_id(self) -> str:
        """Portal primary key of the bill."""
        return self.get("read_id")

    @property
    def fee_month(self) -> str:
        """Billing month, ``YYYY-MM``."""
        return self.get("fee_month")

    @property
    def period_start(self) -> str:
        """Start of the metering period."""
        return self.get("read_date_prev")

    @property
    def period_end(self) -> str:
        """End of the metering period."""
        return self.get("read_date")

    @property
    def amount(self) -> float | None:
        """Fee for this month."""
        return self.num("amount")

    @property
    def usage(self) -> float | None:
        """Gas volume for this month (m3)."""
        return self.num("actual_qty")

    @property
    def price(self) -> float | None:
        """Unit price for this month."""
        return self.num("price")

    @property
    def qty_day(self) -> float | None:
        """Number of metered days."""
        return self.num("qty_day")

    @property
    def daily_average(self) -> float | None:
        """Average daily consumption."""
        usage, days = self.usage, self.qty_day
        if usage is None or not days:
            return None
        return round(usage / days, 2)

    @property
    def meter_reading(self) -> float | None:
        """Meter index at the end of the period."""
        return self.num("current_qty")

    @property
    def previous_reading(self) -> float | None:
        """Meter index at the start of the period."""
        return self.num("before_qty")

    @property
    def status(self) -> str:
        """Payment status as printed by the portal."""
        return self.get("status")

    @property
    def is_paid(self) -> bool:
        """Whether the bill is settled."""
        return "已缴" in self.status or "已支付" in self.status

    def as_dict(self) -> dict[str, Any]:
        """Serialise the bill for service responses and attributes."""
        return {
            "read_id": self.read_id,
            "fee_month": self.fee_month,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "amount": self.amount,
            "usage": self.usage,
            "daily_average": self.daily_average,
            "qty_day": self.qty_day,
            "price": self.price,
            "before_qty": self.previous_reading,
            "current_qty": self.meter_reading,
            "penalty": self.num("penalty_amount"),
            "ladder_amount": self.num("ladder_amount"),
            "sum_amount": self.num("sum_amount"),
            "year_amount": self.num("year_amount"),
            "read_type": self.get("read_type"),
            "status": self.status,
            "title": self.get("bill_title"),
            "meter_number": self.get("meter_number"),
            "name": self.get("name"),
            "address": self.get("address"),
        }


def parse_openid(page: str) -> str:
    """Extract the WeChat openid the portal embedded in the page."""
    for pattern in (r'"openid"\s*:\s*"([^"]+)"', r'OpenId=([A-Za-z0-9_\-]+)'):
        match = re.search(pattern, page)
        if match:
            return match.group(1)
    return ""


def parse_focus_customer_id(page: str) -> str:
    """Extract the account the portal is currently focused on."""
    match = re.search(r'var customerId = "([^"]*)"', page)
    return match.group(1) if match else ""


def parse_accounts(page: str) -> list[Account]:
    """Parse the 户号 list shown on the bill query page."""
    accounts: list[Account] = []
    seen: set[str] = set()

    for tag in re.findall(r"<input[^>]*name=\"userOption\"[^>]*>", page):
        customer_id = _attr(tag, "value")
        entry = Account(
            customer_id=customer_id,
            name=_attr(tag, "data-name"),
            address=_attr(tag, "data-address"),
        )
        if entry.customer_id and entry.customer_id not in seen:
            seen.add(entry.customer_id)
            accounts.append(entry)

    if not accounts:
        for tag in re.findall(r"<option[^>]*>", page):
            customer_id = _attr(tag, "value")
            entry = Account(
                customer_id=customer_id,
                name=_attr(tag, "data-name"),
                address=_attr(tag, "data-address"),
            )
            if entry.customer_id and entry.customer_id not in seen:
                seen.add(entry.customer_id)
                accounts.append(entry)

    return accounts


def parse_bills(page: str) -> list[Bill]:
    """Parse every bill card of the bill list fragment."""
    bills: list[Bill] = []
    for match in re.finditer(r'BtnOpen\((.*?)\)"', page, re.S):
        raw_args = match.group(1)
        args = [html_lib.unescape(a.strip()) for a in re.findall(r"'([^']*)'", raw_args)]
        if len(args) < len(BILL_ARGS):
            continue
        bill = Bill(raw=dict(zip(BILL_ARGS, args)))
        if bill.fee_month and bill.read_id:
            bills.append(bill)

    bills.sort(key=lambda b: b.fee_month, reverse=True)
    return bills


_DETAIL_LABEL_MAP: dict[str, str] = {
    "用户名": "name",
    "用气地址": "address",
    "上次抄表方式": "read_type_prev",
    "上次抄表日期": "read_date_prev",
    "上次抄表度数": "before_qty",
    "本次抄表方式": "read_type",
    "本次抄表日期": "read_date",
    "本次抄表度数": "current_qty",
    "本次用气天数": "qty_day",
    "本次用气量": "actual_qty",
    "用气单价": "price",
    "本月用气金额": "amount",
    "前期未缴气费": "unpaid_prev",
    "违约金": "penalty",
    "本月容量气价": "capacity_price",
    "超档气费": "ladder_amount",
    "合计应缴气费": "sum_amount",
}

_NUMERIC_DETAIL_KEYS = (
    "before_qty",
    "current_qty",
    "qty_day",
    "actual_qty",
    "price",
    "amount",
    "unpaid_prev",
    "penalty",
    "capacity_price",
    "ladder_amount",
    "sum_amount",
)


def parse_bill_detail(page: str) -> dict[str, Any]:
    """Parse the itemised bill page into a flat dict."""
    fields: dict[str, str] = {}
    for block in re.findall(r"<h5[^>]*>(.*?)</h5>", page, re.S):
        text = clean_text(block)
        if ":" not in text and "：" not in text:
            continue
        label, value = re.split(r"[:：]", text, maxsplit=1)
        label = label.strip()
        value = value.strip()
        # The ladder cell carries a "明细" link whose text survives stripping.
        if value.endswith("明细"):
            value = value[: -len("明细")].strip()
        key = None
        for zh_label, mapped in _DETAIL_LABEL_MAP.items():
            if label.startswith(zh_label):
                key = mapped
                break
        if key is None:
            continue
        fields[key] = html_lib.unescape(value)

    result: dict[str, Any] = dict(fields)
    for key in _NUMERIC_DETAIL_KEYS:
        if key in result:
            result[key] = to_float(result[key])

    result["fee_month"] = ""
    result["read_id"] = ""
    read_id = re.search(r"ladderDetail\?FReadId=([0-9A-Za-z]+)", page)
    if read_id:
        result["read_id"] = read_id.group(1)

    period = re.search(r"(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})", page)
    if period:
        result["period_start"] = period.group(1)
        result["period_end"] = period.group(2)
        result["fee_month"] = period.group(2)[:7]

    return result


def parse_usage(page: str) -> dict[str, Any]:
    """Parse the 用气管理 page (summary cards + 6-month bar chart)."""
    result: dict[str, Any] = {}

    title = re.search(r"<h3[^>]*>(.*?)</h3>", page, re.S)
    if title:
        result["title"] = clean_text(title.group(1))

    result["fee_month"] = ""
    month_of_title = re.search(r"(\d{4})年(\d{1,2})月份", result.get("title", ""))
    if month_of_title:
        result["fee_month"] = f"{month_of_title.group(1)}-{int(month_of_title.group(2)):02d}"

    period = re.search(r"(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})", page)
    if period:
        result["period_start"] = period.group(1)
        result["period_end"] = period.group(2)
        if not result["fee_month"]:
            result["fee_month"] = period.group(2)[:7]

    def labelled(label: str) -> str | None:
        pattern = (
            r">\s*" + re.escape(label)
            + r"\s*(?:\([^)]*\)|（[^）]*）)?\s*[:：]?\s*</p>\s*<p[^>]*>(.*?)</p>"
        )
        match = re.search(pattern, page, re.S)
        return clean_text(match.group(1)) if match else None

    result["amount"] = to_float(labelled("本月气费"))
    result["usage"] = to_float(labelled("本月用气量"))
    result["qty_day"] = to_float(labelled("用气天数"))
    result["sum_amount"] = to_float(labelled("本次应缴费用"))

    name_match = re.search(r'\$\(\"#userName\"\)\.text\(\"([^\"]*)\"\)', page)
    result["name"] = clean_text(name_match.group(1)) if name_match else ""

    labels = re.findall(r'labels\.push\("([^"]+)"\)', page)
    values = [to_float(v) for v in re.findall(r"data\.push\(([0-9.]+)\)", page)]
    points = [
        {"month": month, "daily_average": value}
        for month, value in zip(labels, values, strict=False)
    ]
    # The page pushes newest-first then reverses for display.
    points.reverse()
    result["chart"] = points

    if result["usage"] and result["qty_day"]:
        result["daily_average"] = round(result["usage"] / result["qty_day"], 2)
    else:
        result["daily_average"] = None
    return result


def parse_ladder(page: str) -> dict[str, Any]:
    """Parse the tier (阶梯) explanation page."""
    text = clean_text(page)
    tiers: list[dict[str, Any]] = []

    for match in re.finditer(
        r"第([一二三])档，([0-9.]+)(?:-([0-9.]+))?m3?"
        r"(?:（含）|以上)?，?单价([0-9.]+)元/m3",
        text,
    ):
        start = to_float(match.group(2), 0.0) or 0.0
        end = to_float(match.group(3))
        tiers.append(
            {
                "tier": "一二三".index(match.group(1)) + 1,
                "start": start,
                "end": end,
                "price": to_float(match.group(4)),
            }
        )

    note = ""
    note_match = re.search(r"说明\s*(.*?)\s*(?:返回|$)", text)
    if note_match:
        note = note_match.group(1).strip()

    return {"tiers": tiers, "note": note, "text": text}


def tier_for_usage(usage: float | None, tiers: list[dict[str, Any]]) -> int | None:
    """Return the tier a given year-to-date volume falls into."""
    if usage is None or not tiers:
        return None
    for tier in tiers:
        end = tier.get("end")
        if end is None or usage <= float(end):
            return int(tier["tier"])
    return int(tiers[-1]["tier"])
