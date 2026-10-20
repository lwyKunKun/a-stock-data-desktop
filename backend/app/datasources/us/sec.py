import threading
import time

import requests

from app.core.cache import cached
from app.core.source_catalog import source_disclosure

_rate_lock = threading.Lock()
_last_request = 0.0
_TAGS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"),
    "net_income": ("NetIncomeLoss",), "eps_diluted": ("EarningsPerShareDiluted",),
    "assets": ("Assets",), "liabilities": ("Liabilities",),
    "equity": ("StockholdersEquity",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "operating_cashflow": ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByOperatingActivities"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
}


def _headers(contact: str) -> dict:
    value = str(contact or "").strip()
    if not value:
        raise ValueError("未配置 SEC_CONTACT，已跳过 SEC 官方数据")
    return {"User-Agent": f"AStockDataDesktop/0.5 ({value})", "Accept-Encoding": "gzip, deflate"}


def _wait():
    global _last_request
    with _rate_lock:
        gap = 0.2 - (time.monotonic() - _last_request)
        if gap > 0:
            time.sleep(gap)
        _last_request = time.monotonic()


def _get(url: str, contact: str) -> dict:
    _wait()
    response = requests.get(url, headers=_headers(contact), timeout=20)
    response.raise_for_status()
    return response.json()


@cached("us_sec_tickers", ttl=86400)
def ticker_to_cik(symbol: str, contact: str) -> dict:
    mapping = _get("https://www.sec.gov/files/company_tickers.json", contact)
    symbol = symbol.upper().replace(".", "-")
    for item in mapping.values():
        if str(item.get("ticker", "")).upper() == symbol:
            return {"ticker": symbol, "cik": str(item["cik_str"]).zfill(10), "company": item.get("title")}
    raise ValueError("SEC ticker 映射中未找到该公司")


@cached("us_sec_companyfacts", ttl=43200)
def fetch_sec_companyfacts(symbol: str, contact: str) -> dict:
    identity = ticker_to_cik(symbol, contact)
    payload = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{identity['cik']}.json", contact)
    facts = ((payload.get("facts") or {}).get("us-gaap") or {})
    metrics = {}
    for name, candidates in _TAGS.items():
        selected = None
        for tag in candidates:
            if tag in facts:
                selected = (tag, facts[tag])
                break
        if not selected:
            metrics[name] = []
            continue
        tag, fact = selected
        units = fact.get("units") or {}
        preferred = "USD/shares" if name.startswith("eps") else "USD"
        unit = preferred if preferred in units else next(iter(units), None)
        rows = [row for row in (units.get(unit) or []) if row.get("form") in ("10-K", "10-Q")]
        rows.sort(key=lambda row: (row.get("filed") or "", row.get("end") or ""))
        metrics[name] = [
            {"tag": tag, "unit": unit, "start": row.get("start"), "end": row.get("end"),
             "value": row.get("val"), "form": row.get("form"), "filed": row.get("filed"),
             "fy": row.get("fy"), "fp": row.get("fp"), "accn": row.get("accn")}
            for row in rows[-8:]
        ]
    return {
        **identity, "company": payload.get("entityName") or identity.get("company"), "metrics": metrics,
        "sources": [source_disclosure("sec_companyfacts")],
    }
