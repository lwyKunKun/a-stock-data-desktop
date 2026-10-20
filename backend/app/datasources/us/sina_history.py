import json
import re

import requests

from app.core.cache import cached
from app.core.source_catalog import source_disclosure


@cached("us_sina_history", ttl=1800)
def fetch_us_daily_history(symbol: str, num: int = 260) -> dict:
    response = requests.get(
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK",
        params={"symbol": symbol.upper(), "num": num},
        headers={"Referer": "https://finance.sina.com.cn/"},
        timeout=15,
    )
    response.raise_for_status()
    match = re.search(r"\((\[.*\])\)", response.text, flags=re.S)
    if not match:
        raise ValueError("新浪日K返回格式无效")
    rows = json.loads(match.group(1))
    bars = [
        {"date": row.get("d"), "open": float(row.get("o", 0)), "high": float(row.get("h", 0)),
         "low": float(row.get("l", 0)), "close": float(row.get("c", 0)), "volume": int(float(row.get("v", 0) or 0))}
        for row in rows if row.get("d") and row.get("c")
    ]
    if not bars:
        raise ValueError("新浪日K为空")
    return {"symbol": symbol, "bars": bars, "currency": "USD", "sources": [source_disclosure("sina_us_quote", as_of=bars[-1]["date"])]}
