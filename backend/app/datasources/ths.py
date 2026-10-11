"""同花顺数据源 —— 机构一致预期 EPS。

直连 basic.10jqka.com.cn，解析 HTML 表格。零鉴权，仅需 UA + Referer。
"""
from io import StringIO

import pandas as pd
import requests

from app.core.cache import cached
from app.core.ticker import norm_ticker

_THS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://basic.10jqka.com.cn/",
}


@cached("ths_eps", until_eod=True)
def ths_eps_forecast(code: str) -> dict:
    """机构一致预期 EPS。

    返回结构化结果（不返回原始 DataFrame）：
    {covered: bool, analyst_count, eps_cur, eps_next, eps_next2, years: [...]}
    analyst_count < 3 的覆盖度低，估值参考性弱。
    """
    code = norm_ticker(code, stock_only=True)
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    try:
        r = requests.get(url, headers=_THS_HEADERS, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(StringIO(r.text))
    except Exception as e:
        return {"covered": False, "error": f"一致预期请求失败: {e}"}

    # 找含"每股收益"/"均值"的表格
    target = None
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            target = df
            break
    if target is None:
        target = dfs[0] if dfs else None
    if target is None or target.empty:
        return {"covered": False, "note": "无机构覆盖（小盘/次新/ST 常见）"}

    def pick(row, name):
        for c in target.columns:
            if name in str(c):
                v = row.get(c)
                try:
                    return float(v) if pd.notna(v) else None
                except (ValueError, TypeError):
                    return None
        return None

    years = []
    for _, row in target.iterrows():
        years.append({
            "year": str(row.get(target.columns[0], "")),
            "eps_mean": pick(row, "均值"),
            "analyst_count": int(pick(row, "预测机构数") or 0),
        })
    eps_cur = years[0]["eps_mean"] if years else None
    eps_next = years[1]["eps_mean"] if len(years) >= 2 else None
    eps_next2 = years[2]["eps_mean"] if len(years) >= 3 else None
    return {
        "covered": eps_cur is not None,
        "analyst_count": years[0]["analyst_count"] if years else 0,
        "eps_cur": eps_cur, "eps_next": eps_next, "eps_next2": eps_next2,
        "years": years,
    }


@cached("ths_hot", ttl=600)
def ths_hot_list(period: str = "hour") -> list[dict]:
    """同花顺 A 股热榜。period 可选 hour/day。"""
    if period not in {"hour", "day"}:
        raise ValueError("period 须为 hour/day")
    response = requests.get(
        "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
        params={"stock_type": "a", "type": period, "list_type": "normal"},
        headers=_THS_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json() or {}
    data = payload.get("data")
    if not isinstance(data, dict) or "stock_list" not in data:
        raise RuntimeError("同花顺热榜返回结构缺少 data.stock_list")
    rows = []
    for item in data.get("stock_list") or []:
        tag = item.get("tag") or {}
        rows.append({
            "rank": item.get("order"),
            "code": item.get("code") or "",
            "name": item.get("name") or "",
            "heat": item.get("rate"),
            "pct": item.get("rise_and_fall"),
            "rank_chg": item.get("hot_rank_chg"),
            "concepts": tag.get("concept_tag") or [],
            "tag": tag.get("popularity_tag") or "",
        })
    return rows
