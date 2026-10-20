import re

import requests

from app.core.cache import cached
from app.core.instrument import Instrument
from app.core.source_catalog import source_disclosure


@cached("us_sina_quote", ttl=30)
def fetch_us_quote(instrument: Instrument) -> dict:
    response = requests.get(
        f"https://hq.sinajs.cn/list=gb_{instrument.symbol.lower()}",
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    response.encoding = "gbk"
    match = re.search(r'"(.+)"', response.text)
    if not match:
        raise ValueError("新浪未返回有效行情")
    fields = match.group(1).split(",")
    if len(fields) < 27:
        raise ValueError("新浪行情字段不完整")

    def number(index: int):
        try:
            return float(fields[index]) if fields[index] else None
        except (ValueError, IndexError):
            return None

    price = number(1)
    previous_close = number(26)
    return {
        "symbol": instrument.symbol, "name": fields[0], "price": price,
        "previous_close": previous_close, "open": number(5), "high": number(6),
        "low": number(7), "volume": number(10), "high_52w": number(8),
        "low_52w": number(9), "market_cap": number(12), "eps_ttm": number(13),
        "pe_ttm": number(14), "change_pct": number(2),
        "change": price - previous_close if price is not None and previous_close is not None else None,
        "currency": "USD", "as_of": fields[3], "source": "sina_us_quote",
        "sources": [source_disclosure("sina_us_quote", as_of=fields[3])],
    }
