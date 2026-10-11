"""腾讯财经行情源 —— 实时价/PE/PB/市值/换手率/涨跌停/指数/ETF。

HTTP GET，GBK 编码，~ 分隔字段，不封 IP，可放心高频调用。
"""
import urllib.request

from app.core.cache import cached, TTL_REALTIME
from app.core.sslctx import SSL_CONTEXT
from app.core.ticker import get_prefix

_TENCENT_URL = "https://qt.gtimg.cn/q="


def _build_prefixed(codes: list[str]) -> tuple[list[str], dict]:
    """构造带市场前缀的查询键，并记录 key→原始入参 的映射。"""
    prefixed, key_of = [], {}
    for c in codes:
        low = c.lower()
        if low.startswith(("sh", "sz", "bj")):
            p = low
        else:
            p = f"{get_prefix(c)}{c}"
        prefixed.append(p)
        key_of[p] = c
    return prefixed, key_of


def _parse_line(line: str, key_of: dict) -> tuple:
    """解析单行腾讯返回，返回 (原始code, 数据dict) 或 (None, None)。"""
    if not line.strip() or "=" not in line or '"' not in line:
        return None, None
    key = line.split("=")[0].split("_")[-1]
    vals = line.split('"')[1].split("~")
    if len(vals) < 53:
        return None, None

    def f(i):
        return float(vals[i]) if vals[i] else 0.0

    code = key_of.get(key, key[2:])
    q = {
        "name": vals[1],
        "price": f(3),
        "last_close": f(4),
        "open": f(5),
        "change_amt": f(31),
        "change_pct": f(32),
        "high": f(33),
        "low": f(34),
        "amount_wan": f(37),      # 成交额(万)
        "turnover_pct": f(38),    # 换手率%
        "pe_ttm": f(39),
        "amplitude_pct": f(43),   # ⚠️ 43=振幅%，不是 PB
        "float_mcap_yi": f(44),   # 流通市值(亿)
        "mcap_yi": f(45),         # 总市值(亿)
        "pb": f(46),              # ⚠️ PB 在 46
        "limit_up": f(47),
        "limit_down": f(48),
        "vol_ratio": f(49),
        "pe_static": f(52),
    }
    # 僵尸报价检测：成交量 0 且 现价==昨收 → 停牌/废码/未开盘
    q["is_stale"] = (q["amount_wan"] == 0 and q["price"] == q["last_close"]
                     and q["price"] > 0)
    if q["is_stale"] and key[2:4] in ("43", "83", "87"):
        q["stale_reason"] = "北交所老号段，多数已迁至 920xxx，请按名称反查现行代码"
    elif q["is_stale"]:
        q["stale_reason"] = "成交量为 0（停牌/未开盘/废码），报价非当日真实成交"
    return code, q


@cached("quote", ttl=TTL_REALTIME)
def tencent_quote(codes: list[str]) -> dict:
    """批量拉取腾讯实时行情。

    codes: ["688017", "300476"]，也支持指数 ["000300"] 和 ETF ["510300"]。
    返回 {原始code: {name, price, pe_ttm, pb, mcap_yi, ...}}。
    """
    if isinstance(codes, str):
        codes = [codes]
    prefixed, key_of = _build_prefixed(codes)
    req = urllib.request.Request(_TENCENT_URL + ",".join(prefixed))
    req.add_header("User-Agent", "Mozilla/5.0")
    data = urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT).read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        code, q = _parse_line(line, key_of)
        if code is not None:
            result[code] = q
    return result
