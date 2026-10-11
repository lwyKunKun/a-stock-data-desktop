"""东方财富全维度扩展数据源。"""
from collections import Counter
from datetime import datetime, timedelta

from app.core.cache import cached
from app.core.em_client import UA, eastmoney_datacenter, em_get, em_post
from app.core.ticker import em_market_code, em_secid, get_prefix, norm_ticker

_REPORT_API = "https://reportapi.eastmoney.com/report/list"
_ZT_UT = "7eea3edcaed734bea9cbfc24409ed989"
_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}


@cached("stock_info", until_eod=True)
def eastmoney_stock_info(code: str) -> dict:
    code = norm_ticker(code, stock_only=True)
    response = em_get(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={
            "fltt": "2", "invt": "2",
            "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
            "secid": em_secid(code),
        },
        timeout=10,
    )
    response.raise_for_status()
    data = (response.json() or {}).get("data")
    if not isinstance(data, dict):
        raise RuntimeError("东财个股基本面返回结构缺少 data")
    return {
        "code": data.get("f57") or code,
        "name": data.get("f58") or "",
        "industry": data.get("f127") or "",
        "total_shares": data.get("f84") or 0,
        "float_shares": data.get("f85") or 0,
        "mcap": data.get("f116") or 0,
        "float_mcap": data.get("f117") or 0,
        "list_date": str(data.get("f189") or ""),
        "price": data.get("f43") or 0,
    }


@cached("research_reports", until_eod=True)
def eastmoney_reports(code: str, max_pages: int = 1) -> dict:
    code = norm_ticker(code, stock_only=True)
    records = []
    total = 0
    for page in range(1, max_pages + 1):
        response = em_get(
            _REPORT_API,
            params={
                "industryCode": "*", "pageSize": "100", "industry": "*",
                "rating": "*", "ratingChange": "*", "beginTime": "2000-01-01",
                "endTime": "2030-01-01", "pageNo": str(page), "qType": "0",
                "orgCode": "", "code": code, "rcode": "",
            },
            headers={"Referer": "https://data.eastmoney.com/"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json() or {}
        if "data" not in payload:
            raise RuntimeError("东财研报返回结构缺少 data")
        rows = payload.get("data") or []
        total = int(payload.get("hits") or payload.get("TotalCount") or len(rows))
        records.extend(rows)
        if not rows or page >= int(payload.get("TotalPage") or 1):
            break
    items = [{
        "date": str(row.get("publishDate") or "")[:10],
        "org": row.get("orgSName") or "",
        "title": row.get("title") or "",
        "rating": row.get("emRatingName") or "",
        "eps_cur": row.get("predictThisYearEps"),
        "eps_next": row.get("predictNextYearEps"),
        "eps_next2": row.get("predictNextTwoYearEps"),
        "industry": row.get("indvInduName") or "",
    } for row in records]
    ratings = Counter(item["rating"] for item in items if item["rating"])
    return {"total": total, "rating_distribution": dict(ratings), "items": items}


@cached("dragon_tiger", until_eod=True)
def dragon_tiger_records(code: str, trade_date: str, look_back: int = 60) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=(f"(TRADE_DATE>='{start:%Y-%m-%d}')"
                    f"(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")"),
        page_size=50,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    return [{
        "date": str(row.get("TRADE_DATE") or "")[:10],
        "reason": row.get("EXPLANATION") or "",
        "net_buy_wan": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
        "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
    } for row in data]


@cached("lockup", until_eod=True)
def lockup_expiry(code: str, trade_date: str, forward_days: int = 180) -> dict:
    code = norm_ticker(code, stock_only=True)
    end = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
    history_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE", filter_str=f'(SECURITY_CODE="{code}")', page_size=15,
        sort_columns="FREE_DATE", sort_types="-1",
    )
    upcoming_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=(f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{trade_date}\')'
                    f'(FREE_DATE<=\'{end:%Y-%m-%d}\')'),
        page_size=20, sort_columns="FREE_DATE", sort_types="1",
    )

    def normalize(rows):
        return [{
            "date": str(row.get("FREE_DATE") or "")[:10],
            "type": row.get("FREE_SHARES_TYPE") or "",
            "shares": row.get("FREE_SHARES") or 0,
            "able_shares": row.get("ABLE_FREE_SHARES") or 0,
            "ratio": row.get("FREE_RATIO") or 0,
        } for row in rows]

    return {"history": normalize(history_data), "upcoming": normalize(upcoming_data)}


@cached("margin", until_eod=True)
def margin_trading(code: str, page_size: int = 10) -> list[dict]:
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX", filter_str=f'(SCODE="{norm_ticker(code, stock_only=True)}")',
        page_size=page_size, sort_columns="DATE", sort_types="-1",
    )
    return [{
        "date": str(row.get("DATE") or "")[:10],
        "rzye": row.get("RZYE") or 0, "rzmre": row.get("RZMRE") or 0,
        "rzche": row.get("RZCHE") or 0, "rqye": row.get("RQYE") or 0,
        "rqmcl": row.get("RQMCL") or 0, "rqchl": row.get("RQCHL") or 0,
        "rzrqye": row.get("RZRQYE") or 0,
    } for row in data]


@cached("block_trade", until_eod=True)
def block_trade(code: str, page_size: int = 20) -> list[dict]:
    data = eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{norm_ticker(code, stock_only=True)}")',
        page_size=page_size, sort_columns="TRADE_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        close = row.get("CLOSE_PRICE") or 0
        price = row.get("DEAL_PRICE") or 0
        rows.append({
            "date": str(row.get("TRADE_DATE") or "")[:10], "price": price,
            "close": close, "premium_pct": round((price / close - 1) * 100, 2) if close else None,
            "vol": row.get("DEAL_VOLUME") or 0, "amount": row.get("DEAL_AMT") or 0,
            "buyer": row.get("BUYER_NAME") or "", "seller": row.get("SELLER_NAME") or "",
        })
    return rows


@cached("holder_number", until_eod=True)
def holder_num_change(code: str, page_size: int = 8) -> list[dict]:
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{norm_ticker(code, stock_only=True)}")',
        page_size=page_size, sort_columns="END_DATE", sort_types="-1",
    )
    return [{
        "date": str(row.get("END_DATE") or "")[:10],
        "holder_num": row.get("HOLDER_NUM") or 0,
        "change_num": row.get("HOLDER_NUM_CHANGE") or 0,
        "change_ratio": row.get("HOLDER_NUM_RATIO") or 0,
        "avg_shares": row.get("AVG_FREE_SHARES") or 0,
    } for row in data]


@cached("dividend", until_eod=True)
def dividend_history(code: str, page_size: int = 5) -> list[dict]:
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{norm_ticker(code, stock_only=True)}")',
        page_size=page_size, sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    return [{
        "date": str(row.get("EX_DIVIDEND_DATE") or "")[:10],
        "bonus_rmb": row.get("PRETAX_BONUS_RMB") or 0,
        "transfer_ratio": row.get("TRANSFER_RATIO") or 0,
        "bonus_ratio": row.get("BONUS_RATIO") or 0,
        "plan": row.get("ASSIGN_PROGRESS") or "",
    } for row in data]


@cached("fund_flow_rows", ttl=900)
def stock_fund_flow_120d(code: str) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    response = em_get(
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        params={"secid": em_secid(code), "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "lmt": "120"},
        headers={"Referer": "https://quote.eastmoney.com/", "Origin": "https://quote.eastmoney.com"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json() or {}
    if "data" not in payload:
        raise RuntimeError("东财日级资金流返回结构缺少 data")
    rows = []
    for line in (payload.get("data") or {}).get("klines") or []:
        parts = line.split(",")
        if len(parts) >= 6:
            def num(value):
                return float(value) if value not in ("", "-") else 0.0
            rows.append({"date": parts[0], "main_net": num(parts[1]),
                         "small_net": num(parts[2]), "mid_net": num(parts[3]),
                         "large_net": num(parts[4]), "super_net": num(parts[5])})
    return rows


@cached("board_quotes", ttl=300)
def board_quotes(bk_codes: tuple[str, ...]) -> list[dict]:
    codes = [code for code in bk_codes if code]
    if not codes:
        return []
    response = em_get(
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        params={"fltt": "2", "invt": "2", "fields": "f12,f14,f3,f128",
                "secids": ",".join(f"90.{code}" for code in codes)},
        headers={"Referer": "https://quote.eastmoney.com/"}, timeout=15,
    )
    response.raise_for_status()
    data = (response.json() or {}).get("data")
    if not isinstance(data, dict):
        raise RuntimeError("东财板块行情返回结构缺少 data")
    diff = data.get("diff") or []
    items = diff.values() if isinstance(diff, dict) else diff
    return [{"code": item.get("f12") or "", "name": item.get("f14") or "",
             "change_pct": item.get("f3"), "lead_stock": item.get("f128") or ""}
            for item in items]


def _format_zt_time(value) -> str:
    text = str(value or "").zfill(6)
    return f"{text[:2]}:{text[2:4]}:{text[4:6]}" if len(text) == 6 else ""


def _zt_api(endpoint: str, sort: str, date: str) -> list[dict]:
    response = em_get(
        f"https://push2ex.eastmoney.com/{endpoint}",
        params={"ut": _ZT_UT, "dpt": "wz.ztzt", "Pageindex": 0,
                "pagesize": 10000, "sort": sort, "date": date},
        headers={"Referer": "https://quote.eastmoney.com/"}, timeout=10,
    )
    response.raise_for_status()
    payload = response.json() or {}
    if "data" not in payload:
        raise RuntimeError(f"东财 {endpoint} 返回结构缺少 data")
    return (payload.get("data") or {}).get("pool") or []


@cached("zt_pool", ttl=300)
def em_zt_pool(date: str) -> list[dict]:
    return [{"code": row.get("c") or "", "name": row.get("n") or "",
             "price": (row.get("p") or 0) / 1000, "pct": row.get("zdp") or 0,
             "limit_days": row.get("lbc") or 0, "industry": row.get("hybk") or "",
             "first_seal": _format_zt_time(row.get("fbt")), "break_times": row.get("zbc") or 0}
            for row in _zt_api("getTopicZTPool", "fbt:asc", date)]


@cached("zb_pool", ttl=300)
def em_zb_pool(date: str) -> list[dict]:
    return [{"code": row.get("c") or "", "name": row.get("n") or "",
             "pct": row.get("zdp") or 0, "industry": row.get("hybk") or "",
             "break_times": row.get("zbc") or 0}
            for row in _zt_api("getTopicZBPool", "fbt:asc", date)]


@cached("dt_pool", ttl=300)
def em_dt_pool(date: str) -> list[dict]:
    return [{"code": row.get("c") or "", "name": row.get("n") or "",
             "pct": row.get("zdp") or 0, "industry": row.get("hybk") or ""}
            for row in _zt_api("getTopicDTPool", "fund:asc", date)]


@cached("sentiment", ttl=300)
def limit_up_sentiment(date: str = "") -> dict:
    if date:
        actual = date.replace("-", "")
        zt = em_zt_pool(actual)
    else:
        actual, zt = "", []
        today = datetime.now()
        for offset in range(8):
            candidate = (today - timedelta(days=offset)).strftime("%Y%m%d")
            zt = em_zt_pool(candidate)
            if zt:
                actual = candidate
                break
        if not actual:
            actual = today.strftime("%Y%m%d")
    zb, dt = em_zb_pool(actual), em_dt_pool(actual)
    ladder = Counter(int(row.get("limit_days") or 0) for row in zt)
    ladder.pop(0, None)
    total = len(zt) + len(zb)
    return {"date": actual, "zt_count": len(zt), "zb_count": len(zb),
            "dt_count": len(dt), "break_rate": round(len(zb) / total * 100, 1) if total else 0,
            "max_height": max((row.get("limit_days") or 0 for row in zt), default=0),
            "ladder": dict(sorted(ladder.items())), "zt_pool": zt, "zb_pool": zb, "dt_pool": dt}


@cached("em_hot_rank", ttl=600)
def em_hot_rank(top: int = 100) -> list[dict]:
    response = em_post(
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
        json={**_HOT_BODY, "marketType": "", "pageNo": 1, "pageSize": top},
        timeout=10,
    )
    response.raise_for_status()
    data = (response.json() or {}).get("data")
    if data is None:
        raise RuntimeError("东财人气榜返回结构缺少 data")
    return [{"rank": row.get("rk"), "code": str(row.get("sc") or "")[2:],
             "market_code": row.get("sc") or "", "rank_chg": row.get("hisRc")}
            for row in data]


@cached("em_hot_concept", ttl=600)
def em_hot_concept(code: str) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    response = em_post(
        "https://emappdata.eastmoney.com/stockrank/getHotStockRankList",
        json={**_HOT_BODY, "srcSecurityCode": get_prefix(code).upper() + code}, timeout=10,
    )
    response.raise_for_status()
    data = (response.json() or {}).get("data")
    if data is None:
        raise RuntimeError("东财热门概念返回结构缺少 data")
    return [{"concept": row.get("conceptName") or "", "bk": row.get("conceptId") or "",
             "hit": row.get("hitCount") or 0} for row in data]
