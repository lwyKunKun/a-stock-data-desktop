"""估值服务 —— 组合行情 + 一致预期，服务端算出结论性指标。

这是「服务端出结论而非透传原始数据」的典型：调用方拿到的直接是
前向PE / PEG / PE消化年限 / 估值判断，不需要自己再算，也不喂原始数据给 AI。
"""
import math

from app.datasources.tencent import tencent_quote
from app.datasources.ths import ths_eps_forecast

# A股成长股合理估值锚点，所有行业统一用 30x
TARGET_PE = 30


def forward_pe(price: float, eps_forecast: float):
    """前向PE = 当前股价 / 未来年度一致预期EPS。"""
    if not eps_forecast or eps_forecast <= 0:
        return None
    return round(price / eps_forecast, 1)


def pe_digestion(current_pe: float, cagr: float, target_pe: float = TARGET_PE):
    """当前PE消化到目标PE需要多少年。cagr = 下一年EPS/当年EPS - 1。"""
    if not current_pe or current_pe <= target_pe:
        return 0.0
    if not cagr or cagr <= 0:
        return None  # 负增长无法消化
    return round(math.log(current_pe / target_pe) / math.log(1 + cagr), 1)


def calc_peg(pe: float, cagr: float):
    """PEG = 前向PE / (CAGR * 100)。<1 便宜，1~1.5 合理，>1.5 贵。"""
    if not pe or not cagr or cagr <= 0:
        return None
    return round(pe / (cagr * 100), 2)


def peg_verdict(peg):
    if peg is None:
        return "无法计算（缺一致预期或负增长）"
    if peg < 1:
        return "便宜"
    if peg <= 1.5:
        return "合理"
    return "偏贵"


def valuation_from_inputs(code: str, q: dict, eps: dict) -> dict:
    """使用已获取的行情与一致预期计算估值，避免聚合器重复请求。"""
    if not q:
        return {"error": f"未取到 {code} 的行情"}
    price = q["price"]
    eps_cur, eps_next = eps.get("eps_cur"), eps.get("eps_next")

    pe_fwd = forward_pe(price, eps_cur) if eps_cur else None
    cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next) else None
    peg = calc_peg(pe_fwd, cagr) if (pe_fwd and cagr) else None
    digest = pe_digestion(pe_fwd, cagr) if (pe_fwd and cagr) else None

    return {
        "code": code,
        "name": q["name"],
        "price": price,
        "is_stale": q.get("is_stale", False),
        "mcap_yi": q["mcap_yi"],
        "pe_ttm": q["pe_ttm"],
        "pe_static": q["pe_static"],
        "pb": q["pb"],
        "turnover_pct": q["turnover_pct"],
        "covered": eps.get("covered", False),
        "analyst_count": eps.get("analyst_count", 0),
        "eps_cur": eps_cur, "eps_next": eps_next,
        "pe_fwd": pe_fwd,
        "cagr_pct": round(cagr * 100, 1) if cagr else None,
        "peg": peg,
        "peg_verdict": peg_verdict(peg),
        "digest_years": digest,
    }


def full_valuation(code: str) -> dict:
    """单票完整估值 —— 一个调用拿全部结论性指标。"""
    quotes = tencent_quote([code])
    q = quotes.get(code) or next(iter(quotes.values()), None)
    return valuation_from_inputs(code, q, ths_eps_forecast(code))
