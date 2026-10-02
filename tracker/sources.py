"""Fetchers for public data. Each fetch_* does network I/O; each parse_* is pure.

Every fetcher may fail (rate limits, bot blocking, format changes). Callers
treat a failure as "no data today" and fall back to data/manual.json.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d"
# CFTC Disaggregated Futures-Only report; 084691 is COMEX silver.
CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_SILVER_CODE = "084691"
CME_STOCKS_URL = "https://www.cmegroup.com/delivery_reports/Silver_stocks.xls"


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# --- Yahoo Finance daily closes (SI=F silver, GC=F gold, CNY=X USD/CNY) ---

def parse_yahoo_chart(payload: dict) -> dict[str, float]:
    """Return {YYYY-MM-DD: close} from a Yahoo v8 chart response."""
    result = payload["chart"]["result"][0]
    stamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0].get("close") or []
    out = {}
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        day = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()
        out[day] = float(close)
    return out


def fetch_yahoo_closes(symbol: str, range_: str = "1y") -> dict[str, float]:
    url = YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol), range=range_)
    return parse_yahoo_chart(json.loads(_get(url)))


# --- CFTC Commitments of Traders (weekly) ---

def _field(row: dict, prefix: str) -> float | None:
    """Look up a Socrata column by prefix, ignoring doubled underscores.

    The dataset's column names are inconsistent (e.g. swap__positions_short_all),
    so match on a normalised prefix rather than an exact name.
    """
    for key, value in row.items():
        if re.sub(r"_+", "_", key).startswith(prefix):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def parse_cot_rows(rows: list[dict]) -> list[dict]:
    """Normalise CFTC rows to {date, open_interest, mm_net, commercial_net_short}."""
    out = []
    for row in rows:
        date = str(row.get("report_date_as_yyyy_mm_dd", ""))[:10]
        oi = _field(row, "open_interest_all")
        pm_long = _field(row, "prod_merc_positions_long")
        pm_short = _field(row, "prod_merc_positions_short")
        sw_long = _field(row, "swap_positions_long")
        sw_short = _field(row, "swap_positions_short")
        mm_long = _field(row, "m_money_positions_long")
        mm_short = _field(row, "m_money_positions_short")
        if not date or oi is None:
            continue
        rec = {"date": date, "open_interest": oi, "mm_net": None, "commercial_net_short": None}
        if mm_long is not None and mm_short is not None:
            rec["mm_net"] = mm_long - mm_short
        if None not in (pm_long, pm_short, sw_long, sw_short):
            rec["commercial_net_short"] = (pm_short - pm_long) + (sw_short - sw_long)
        out.append(rec)
    out.sort(key=lambda r: r["date"])
    return out


def fetch_cot(limit: int = 60) -> list[dict]:
    query = urllib.parse.urlencode({
        "cftc_contract_market_code": CFTC_SILVER_CODE,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(limit),
    })
    return parse_cot_rows(json.loads(_get(f"{CFTC_URL}?{query}")))


# --- CME/COMEX warehouse stocks (daily) ---

def _to_number(cell) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def parse_cme_stock_rows(rows: list[list]) -> dict[str, float]:
    """Pull total registered/eligible ounces out of the Silver_stocks sheet.

    The totals rows are labelled e.g. "TOTAL REGISTERED"; the last numeric cell
    on the row is today's total.
    """
    out = {}
    for row in rows:
        label = " ".join(str(c) for c in row if isinstance(c, str)).upper()
        numbers = [n for n in (_to_number(c) for c in row) if n is not None]
        if not numbers:
            continue
        if "TOTAL REGISTERED" in label:
            out["registered_oz"] = numbers[-1]
        elif "TOTAL ELIGIBLE" in label:
            out["eligible_oz"] = numbers[-1]
    return out


def _html_table_rows(text: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)
        rows.append([re.sub(r"<[^>]+>", "", c).strip() for c in cells])
    return rows


def fetch_cme_stocks() -> dict[str, float]:
    raw = _get(CME_STOCKS_URL)
    if raw.lstrip()[:1] == b"<":  # CME sometimes serves the "xls" as an HTML table
        return parse_cme_stock_rows(_html_table_rows(raw.decode("utf-8", "replace")))
    import xlrd  # optional dependency, only needed for the binary .xls format

    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    return parse_cme_stock_rows([sheet.row_values(i) for i in range(sheet.nrows)])
