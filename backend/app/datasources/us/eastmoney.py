import requests

from app.core.cache import cached
from app.core.instrument import Instrument
from app.core.source_catalog import source_disclosure

_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _get(report_name: str, secucode: str, page_size: int = 100) -> list[dict]:
    response = requests.get(
        _DATACENTER,
        params={
            "reportName": report_name, "columns": "ALL", "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": 1, "pageSize": page_size, "sortColumns": "REPORT_DATE", "sortTypes": -1,
            "source": "WEB", "client": "WEB",
        },
        headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
    )
    response.raise_for_status()
    return ((response.json().get("result") or {}).get("data") or [])


def _secucodes(instrument: Instrument):
    return (f"{instrument.symbol}.O", f"{instrument.symbol}.N")


@cached("us_em_fundamentals", ttl=21600)
def fetch_us_fundamentals(instrument: Instrument) -> dict:
    result = {"indicators": [], "income": [], "balance": [], "cashflow": []}
    report_names = {
        "indicators": "RPT_USF10_FN_GMAININDICATOR", "income": "RPT_USF10_FN_INCOME",
        "balance": "RPT_USF10_FN_BALANCE", "cashflow": "RPT_USSK_FN_CASHFLOW",
    }
    selected = None
    for secucode in _secucodes(instrument):
        indicators = _get(report_names["indicators"], secucode, 8)
        if indicators:
            selected, result["indicators"] = secucode, indicators
            break
    if selected:
        for key in ("income", "balance", "cashflow"):
            result[key] = _get(report_names[key], selected, 120)
    if not selected:
        raise ValueError("东方财富未匹配到该美股的财务代码")
    result.update({"secucode": selected, "sources": [source_disclosure("eastmoney_us")]})
    return result
