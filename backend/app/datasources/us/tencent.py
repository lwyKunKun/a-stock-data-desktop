import re

import requests

from app.core.cache import cached
from app.core.instrument import Instrument
from app.core.source_catalog import source_disclosure


@cached("us_tencent_quote", ttl=30)
def fetch_us_quote(instrument: Instrument) -> dict:
    response = requests.get(f"https://qt.gtimg.cn/q=us{instrument.symbol}", timeout=10)
    response.raise_for_status()
    response.encoding = "gbk"
    match = re.search(r'"(.+)"', response.text)
    if not match:
        raise ValueError("腾讯未返回有效行情")
    fields = match.group(1).split("~")
    if len(fields) < 52:
        raise ValueError("腾讯行情字段不完整")

    def number(index: int):
        try:
            return float(fields[index]) if fields[index] else None
        except (ValueError, IndexError):
            return None

    price, previous_close = number(3), number(4)
    return {
        "symbol": instrument.symbol, "name": fields[46] or fields[1], "name_zh": fields[1],
        "price": price, "previous_close": previous_close, "open": number(5),
        "volume": int(number(6) or 0), "high": number(33), "low": number(34),
        "change_pct": number(32), "change": price - previous_close if price is not None and previous_close is not None else None,
        "currency": fields[35] or "USD", "pe_ttm": number(39), "pb": number(51),
        "market_cap_hundred_million": number(45), "eps_ttm": number(47),
        "high_52w": number(48), "low_52w": number(49), "as_of": fields[30],
        "source": "tencent_us_quote",
        "sources": [source_disclosure("tencent_us_quote", as_of=fields[30])],
    }
