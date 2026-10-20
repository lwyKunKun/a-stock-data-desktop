from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from app.core.instrument import Instrument
from app.core.source_catalog import source_disclosure
from app.datasources.us.eastmoney import fetch_us_fundamentals
from app.datasources.us.sec import fetch_sec_companyfacts
from app.datasources.us.sina import fetch_us_quote as fetch_sina_quote
from app.datasources.us.sina_history import fetch_us_daily_history
from app.datasources.us.tencent import fetch_us_quote as fetch_tencent_quote
from app.datasources.us.yahoo_chart import fetch_yahoo_chart
from app.datasources.us.yahoo_summary import fetch_yahoo_summary
from app.services.technical_indicators import calculate_technical_indicators


def _call(name: str, fn, *args):
    try:
        return name, fn(*args), None
    except Exception as exc:
        return name, None, str(exc)


def build_us_snapshot(
    instrument: Instrument,
    on_progress: Optional[Callable[[dict], None]] = None,
    sec_contact: str = "",
) -> dict:
    jobs = {
        "sina_quote": (fetch_sina_quote, instrument),
        "tencent_quote": (fetch_tencent_quote, instrument),
        "history": (fetch_yahoo_chart, instrument.yahoo_symbol or instrument.symbol),
        "sina_history": (fetch_us_daily_history, instrument.symbol),
        "yahoo_summary": (fetch_yahoo_summary, instrument),
        "eastmoney": (fetch_us_fundamentals, instrument),
    }
    if sec_contact:
        jobs["sec"] = (fetch_sec_companyfacts, instrument.symbol, sec_contact)
    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_call, key, fn, *args): key for key, (fn, *args) in jobs.items()}
        done = 0
        for future in as_completed(futures):
            name, value, error = future.result()
            done += 1
            if error:
                errors[name] = error
            else:
                results[name] = value
            if on_progress:
                on_progress({"current_chapter": f"正在采集美股数据：{name}", "progress": {"done": min(done, 9), "total": 10}})
    if not sec_contact:
        errors["sec"] = "未配置 SEC_CONTACT，已跳过 SEC 官方数据；其他数据不受影响"
    else:
        errors.pop("sec", None)

    quote = results.get("tencent_quote") or results.get("sina_quote") or {}
    history = results.get("history") or {}
    if not history.get("bars"):
        history = results.get("sina_history") or {}
        if history.get("bars") and history.get("currency") is None:
            history["currency"] = "USD"
    if not quote and not history.get("bars"):
        raise RuntimeError("美股核心行情与 K 线均获取失败")
    yahoo = results.get("yahoo_summary") or {}
    eastmoney = results.get("eastmoney") or {}
    sec = results.get("sec") or {"available": False, "note": errors.get("sec")}
    profile = yahoo.get("profile") or {}
    name = profile.get("name") or quote.get("name") or sec.get("company") or instrument.symbol
    currency = quote.get("currency") or profile.get("currency") or history.get("currency") or "USD"
    technical = calculate_technical_indicators(history.get("bars") or [])
    indicators = (eastmoney.get("indicators") or [])
    indicator_latest = indicators[0] if indicators else {}
    profile.setdefault("name", name)
    profile.setdefault("exchange", quote.get("exchange") or sec.get("exchange") or "")
    profile.setdefault("industry", indicator_latest.get("ORG_INDUSTRY") or "")
    profile.setdefault("sector", indicator_latest.get("ORG_INDUSTRY") or "")
    profile.setdefault("currency", indicator_latest.get("CURRENCY_ABBR") or currency)
    sources = []
    for value in results.values():
        sources.extend(value.get("sources") or [])
    if not sec_contact:
        sources.append(source_disclosure("sec_companyfacts", status="skipped"))

    chapters = {
        "us_ch1_quote": {"quote": quote},
        "us_ch2_price_trend": {"history": history, "latest": technical.get("latest") or {}},
        "us_ch3_technical": technical,
        "us_ch4_profile": {"profile": profile, "cik": sec.get("cik")},
        "us_ch5_valuation": {"valuation": yahoo.get("valuation") or {}, "quote": quote, "indicators": indicators},
        "us_ch6_income": {"yahoo": (yahoo.get("financials") or {}).get("income") or [], "eastmoney": eastmoney.get("income") or [], "sec": (sec.get("metrics") or {}).get("revenue") or []},
        "us_ch7_balance": {"yahoo": (yahoo.get("financials") or {}).get("balance") or [], "eastmoney": eastmoney.get("balance") or [], "sec": {key: value for key, value in (sec.get("metrics") or {}).items() if key in ("assets", "liabilities", "equity", "cash")}},
        "us_ch8_cashflow": {"yahoo": (yahoo.get("financials") or {}).get("cashflow") or [], "eastmoney": eastmoney.get("cashflow") or [], "sec": {key: value for key, value in (sec.get("metrics") or {}).items() if key in ("operating_cashflow", "capex")}},
        "us_ch9_sec_facts": {"sec": sec, "sources": sources, "source_errors": errors},
        "us_ch10_summary": {},
    }
    chapter_errors = {key: list(errors.values()) for key in chapters if errors}
    return {
        "market": "US", "instrument": {"market": "US", "symbol": instrument.symbol,
        "canonical_key": instrument.canonical_key, "exchange": profile.get("exchange"), "asset_type": instrument.asset_type},
        "code": instrument.symbol, "name": name, "currency": currency, "chapters": chapters,
        "sources": sources, "errors": chapter_errors, "source_errors": errors,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
