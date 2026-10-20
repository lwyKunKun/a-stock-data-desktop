import subprocess
from urllib.parse import quote

import json

from app.core.cache import cached
from app.core.source_catalog import source_disclosure


@cached("us_stock_search", ttl=21600)
def search_us_stocks(query: str, limit: int = 10) -> dict:
    # 东财对 Python requests 的 UA 会返回 JSONP 空结构；用 curl 伪装浏览器可获得原始 JSON。
    url = (
        "https://searchapi.eastmoney.com/api/suggest/get?"
        f"input={quote(query)}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8&count={limit}"
    )
    response = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=15)
    text = response.stdout.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"搜索接口返回非JSON内容: {text[:120]}")
    data = json.loads(text[start:end + 1])
    rows = ((data.get("QuotationCodeTable") or {}).get("Data") or [])
    markets = {"105": "NASDAQ", "106": "NYSE", "107": "US_OTHER"}
    items = []
    for row in rows:
        market = str(row.get("MktNum", ""))
        if market not in markets:
            continue
        security_type = str(row.get("SecurityTypeName") or "")
        security_code = str(row.get("SecurityType") or "")
        if any(word in security_type.upper() for word in ("ETF", "INDEX", "OPTION")):
            continue
        if security_code != "20":
            continue
        items.append({
            "symbol": row.get("Code"), "name": row.get("Name"), "exchange": markets[market],
            "asset_type": "stock", "market": "US",
        })
    return {"query": query, "items": items[:limit], "sources": [source_disclosure("eastmoney_us")]}
