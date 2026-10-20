from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from app.core.cache import cached
from app.core.source_catalog import source_disclosure


@cached("us_yahoo_chart", ttl=1800)
def fetch_yahoo_chart(symbol: str, interval: str = "1d", range_: str = "1y") -> dict:
    response = requests.get(
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"interval": interval, "range": range_, "events": "div,split"},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
    )
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("Yahoo 未返回 K 线")
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adjusted = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    try:
        exchange_tz = ZoneInfo(meta.get("exchangeTimezoneName") or "America/New_York")
    except ZoneInfoNotFoundError:
        exchange_tz = timezone(timedelta(seconds=meta.get("gmtoffset") or 0))

    bars = []
    for index, timestamp in enumerate(timestamps):
        close_values = quote.get("close") or []
        if index >= len(close_values) or close_values[index] is None:
            continue

        def value(key: str):
            values = quote.get(key) or []
            raw = values[index] if index < len(values) else None
            return float(f"{raw:.7g}") if raw is not None else None

        bar = {
            "date": datetime.fromtimestamp(timestamp, exchange_tz).strftime("%Y-%m-%d"),
            "open": value("open"), "high": value("high"), "low": value("low"),
            "close": value("close"), "volume": int(value("volume") or 0),
        }
        if index < len(adjusted) and adjusted[index] is not None:
            bar["adj_close"] = float(f"{adjusted[index]:.7g}")
        if bars and bars[-1]["date"] == bar["date"]:
            bars[-1] = bar
        else:
            bars.append(bar)
    if not bars:
        raise ValueError("Yahoo K 线为空")
    return {
        "symbol": symbol, "bars": bars, "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"), "timezone": meta.get("exchangeTimezoneName"),
        "sources": [source_disclosure("yahoo_chart", as_of=bars[-1]["date"])],
    }
