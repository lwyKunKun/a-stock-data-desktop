"""新浪财经备用源 —— 东财被封时的降级链路。

东财 push2/push2his 对部分大陆住宅 IP 有间歇性连接级风控（RemoteDisconnected/HTTP 000），
非代码问题，几分钟到数小时自动恢复。但为保证服务可用性，日级资金流走新浪备胎降级
（不同域名、不同风控面，东财被封时不受牵连）。
"""
import json
import urllib.request

from app.core.sslctx import SSL_CONTEXT
from app.core.ticker import get_prefix

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fund_flow_backup(code: str, days: int = 60) -> list:
    """个股资金流备用源（新浪，日度主力净额）。

    返回 [{date, close, net_amount(主力净流入,元), turnover}]，按日期升序。
    取不到时返回 []（由调用方决定如何降级）。
    """
    pre = f"{get_prefix(code)}{code}"
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Referer": "https://finance.sina.com.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as r:
            t = r.read().decode("utf-8", "ignore")
        arr = json.loads(t[t.index("["):t.rindex("]") + 1])
    except Exception:
        return []
    rows = [{"date": x.get("opendate"), "close": x.get("trade"),
             "net_amount": float(x.get("netamount") or 0),
             "turnover": x.get("turnover")} for x in arr]
    rows.sort(key=lambda x: x["date"] or "")  # 新浪默认降序，统一转升序
    return rows
