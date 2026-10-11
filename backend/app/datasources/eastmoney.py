"""东方财富数据源 —— 资金流（分钟级/日级聚合）+ 板块归属。

⚠️ 所有请求走 em_get() 限流防封。
⚠️ 本模块的关键设计：日级资金流在服务端聚合成 5/20/60 日三个数，
   不把 120 天逐日明细返回给调用方（省带宽、省 AI token）。
"""
from app.core.cache import cached
from app.core.em_client import em_get, UA
from app.core.ticker import em_secid, em_market_code


@cached("fflow_min", ttl=30)
def fund_flow_minute(code: str) -> dict:
    """个股当日分钟级资金流。

    返回聚合结果，不返回逐分钟明细：
    {points, main_net_total(全天主力净流入,元), last(最新一分钟), signal}
    """
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": em_secid(code), "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    try:
        d = em_get(url, params=params, headers=headers, timeout=10).json()
    except Exception:
        # 东财分钟资金流为独家数据、无备用源。住宅 IP 间歇风控时连接被重置，
        # 属临时现象（几分钟~数小时自动恢复），返回友好提示而非原始堆栈。
        return {"available": False,
                "note": "分钟级资金流暂不可用（东财接口临时风控，稍后自动恢复）；"
                        "日级资金流已走新浪备胎，见 daily 字段"}

    klines = (d.get("data") or {}).get("klines") or []
    # ⚠️ 东财分钟资金流 f52(主力净额) 是【当日累计值】（从开盘逐分钟累加），
    #    不是每分钟增量。全天净流入 = 最后一个点的值，绝不能对累计值再求和
    #    （否则会得到 ~10 倍于成交额的错误数字）。
    main_total = 0.0
    last = None
    for line in klines:
        p = line.split(",")
        if len(p) >= 6:
            main_total = float(p[1])   # 取最新累计值（覆盖而非累加）
            last = {"time": p[0], "main_net_cum": float(p[1]),
                    "super_net_cum": float(p[5])}
    return {
        "points": len(klines),
        "main_net_total": round(main_total, 0),          # 元
        "main_net_total_wan": round(main_total / 1e4, 1),  # 万元
        "last": last,
        "signal": "bullish" if main_total > 0 else "bearish",
    }


def _em_fund_flow_raw(code: str) -> list:
    """东财日级资金流原始序列 [{date, main_net}]；失败/空返回 []。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": em_secid(code),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    try:
        d = em_get(url, params=params, headers=headers, timeout=15).json()
    except Exception:
        return []
    daily = []
    for line in (d.get("data") or {}).get("klines") or []:
        p = line.split(",")
        if len(p) >= 7:
            daily.append({"date": p[0],
                          "main_net": float(p[1]) if p[1] != "-" else 0.0})
    return daily


@cached("fflow_day", until_eod=True)
def fund_flow_daily(code: str) -> dict:
    """个股日级资金流，服务端聚合成 5/20/60 日。主源东财，失败降级新浪。

    返回：{source, windows: {"5d":主力净额, "20d":..., "60d":...}, trend}
    单位：元。不返回逐日明细。
    """
    daily = _em_fund_flow_raw(code)
    source = "eastmoney"
    if not daily:
        # 降级：东财被封/返空 → 新浪备用源（不同域名、不同风控面）
        from app.datasources.sina import fund_flow_backup
        backup = fund_flow_backup(code, days=60)
        daily = [{"date": x["date"], "main_net": x["net_amount"]} for x in backup]
        source = "sina_backup"
    if not daily:
        return {"windows": {}, "source": "none",
                "note": "东财与新浪均未取到日级资金流（可能是 ETF 或网络波动）"}

    def window_sum(n):
        return round(sum(x["main_net"] for x in daily[-n:]), 0)

    windows = {
        "5d": window_sum(5),
        "20d": window_sum(20),
        "60d": window_sum(60),
        "total_days": len(daily),
    }
    # 简单趋势判断：短期 vs 中期方向
    trend = "流入" if windows["5d"] > 0 and windows["20d"] > 0 else \
            "流出" if windows["5d"] < 0 and windows["20d"] < 0 else "分歧"
    return {"windows": windows, "trend": trend, "source": source,
            "latest_date": daily[-1]["date"]}


@cached("concept", until_eod=True)
def concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属（东财 slist，一次拿全）。

    返回：{total, tags: [板块名...], boards: [{name, code, change_pct, lead_stock}]}
    """
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{em_market_code(code)}.{code}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        d = em_get("https://push2.eastmoney.com/api/qt/slist/get",
                   params=params, headers=headers, timeout=15).json()
    except Exception as e:
        return {"error": f"板块归属请求失败: {e}"}

    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = [{"name": it.get("f14", ""), "code": it.get("f12", ""),
               "change_pct": it.get("f3", ""), "lead_stock": it.get("f128", "")}
              for it in items]
    return {"total": len(boards),
            "tags": [b["name"] for b in boards],
            "boards": boards}
