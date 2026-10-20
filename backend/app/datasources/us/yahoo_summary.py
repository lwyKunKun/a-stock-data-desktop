import threading

import requests

from app.core.cache import cached
from app.core.instrument import Instrument
from app.core.source_catalog import source_disclosure

_lock = threading.Lock()
_session: requests.Session | None = None
_crumb = ""


def _session_with_crumb(force: bool = False) -> tuple[requests.Session, str]:
    global _session, _crumb
    with _lock:
        if _session is not None and _crumb and not force:
            return _session, _crumb
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        session.get("https://fc.yahoo.com", timeout=10)
        response = session.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        response.raise_for_status()
        crumb = response.text.strip()
        if not crumb:
            raise ValueError("Yahoo crumb 为空")
        _session, _crumb = session, crumb
        return session, crumb


def _raw(value):
    if isinstance(value, dict):
        return value.get("raw", value.get("fmt"))
    return value


@cached("us_yahoo_summary", ttl=3600)
def fetch_yahoo_summary(instrument: Instrument) -> dict:
    modules = (
        "assetProfile,price,financialData,defaultKeyStatistics,summaryDetail,"
        "incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory"
    )
    last_error = None
    for refresh in (False, True):
        try:
            session, crumb = _session_with_crumb(force=refresh)
            response = session.get(
                f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{instrument.yahoo_symbol}",
                params={"modules": modules, "crumb": crumb}, timeout=15,
            )
            if response.status_code in (401, 403) and not refresh:
                continue
            response.raise_for_status()
            result = ((response.json().get("quoteSummary") or {}).get("result") or [{}])[0]
            profile, price = result.get("assetProfile") or {}, result.get("price") or {}
            financial, stats, detail = result.get("financialData") or {}, result.get("defaultKeyStatistics") or {}, result.get("summaryDetail") or {}

            def rows(module: str, key: str):
                values = (result.get(module) or {}).get(key) or []
                return [{name: _raw(value) for name, value in row.items()} for row in values]

            return {
                "profile": {
                    "name": _raw(price.get("longName")) or _raw(price.get("shortName")),
                    "exchange": _raw(price.get("exchangeName")) or _raw(price.get("exchange")),
                    "currency": _raw(price.get("currency")) or "USD", "sector": profile.get("sector"),
                    "industry": profile.get("industry"), "country": profile.get("country"),
                    "website": profile.get("website"), "description": profile.get("longBusinessSummary"),
                },
                "valuation": {
                    "market_cap": _raw(price.get("marketCap")), "enterprise_value": _raw(stats.get("enterpriseValue")),
                    "pe_ttm": _raw(detail.get("trailingPE")), "pe_forward": _raw(detail.get("forwardPE")),
                    "pb": _raw(stats.get("priceToBook")), "ps_ttm": _raw(detail.get("priceToSalesTrailing12Months")),
                    "eps_ttm": _raw(stats.get("trailingEps")), "eps_forward": _raw(stats.get("forwardEps")),
                    "dividend_yield": _raw(detail.get("dividendYield")), "revenue_growth": _raw(financial.get("revenueGrowth")),
                },
                "financials": {
                    "income": rows("incomeStatementHistory", "incomeStatementHistory"),
                    "balance": rows("balanceSheetHistory", "balanceSheetStatements"),
                    "cashflow": rows("cashflowStatementHistory", "cashflowStatements"),
                },
                "sources": [source_disclosure("yahoo_summary")],
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Yahoo 基本面获取失败: {last_error}")
