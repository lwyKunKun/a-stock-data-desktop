"""全维度数据聚合器 —— AI 分析的数据底座。

职责：把散落在各数据源的信息并发抓齐、压缩成一份结构化「个股全景快照」。
这份快照有两处用途：
1. 前端「个股详情」页直接展示（零 token）
2. 序列化成紧凑文本喂给 DeepSeek 做 AI 分析（P2）

⚠️ 省 token 的关键：这里只做「聚合 + 精简」，不返回原始逐条明细。
   例如资金流只给 5/20/60 日三个窗口值，不给 120 天逐日数据。
"""
from concurrent.futures import ThreadPoolExecutor

from app.datasources.tencent import tencent_quote
from app.datasources.eastmoney import fund_flow_minute, fund_flow_daily, concept_blocks
from app.datasources.ths import ths_eps_forecast
from app.services.valuation import full_valuation


def _safe(fn, *args, **kwargs):
    """并发子任务的兜底：单个数据源失败不拖垮整个快照。"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"error": f"{fn.__name__} 失败: {e}"}


def build_snapshot(code: str) -> dict:
    """并发抓取全维度数据，返回个股全景快照。

    并发说明：东财请求虽走 em_get 串行限流，但腾讯/同花顺/东财分属不同域名，
    用线程池并发可把总耗时从「各源之和」压到「最慢的那个」。
    """
    # 并发抓取五个维度（估值内部已含行情+EPS，这里额外单拉行情做展示）
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_quote = pool.submit(_safe, tencent_quote, [code])
        f_val = pool.submit(_safe, full_valuation, code)
        f_ff_min = pool.submit(_safe, fund_flow_minute, code)
        f_ff_day = pool.submit(_safe, fund_flow_daily, code)
        f_concept = pool.submit(_safe, concept_blocks, code)

    quote = f_quote.result()
    q = quote.get(code) if isinstance(quote, dict) else None

    return {
        "code": code,
        "quote": q or {},                       # 实时行情（腾讯）
        "valuation": f_val.result(),            # 估值结论（前向PE/PEG/消化）
        "fund_flow_minute": f_ff_min.result(),  # 当日分钟级资金流
        "fund_flow_daily": f_ff_day.result(),   # 日级资金流(5/20/60日聚合)
        "concept": f_concept.result(),          # 板块/概念归属
    }


def snapshot_to_prompt_text(snap: dict) -> str:
    """把快照序列化成喂给 AI 的紧凑文本（控制在 ~1500 token 内）。

    只保留对投资判断有意义的字段，去掉冗余键名，用中文标签。
    """
    q = snap.get("quote") or {}
    v = snap.get("valuation") or {}
    ffm = snap.get("fund_flow_minute") or {}
    ffd = snap.get("fund_flow_daily") or {}
    c = snap.get("concept") or {}

    lines = [f"股票：{v.get('name', q.get('name', snap['code']))}（{snap['code']}）"]

    # 行情
    if q:
        lines.append(
            f"行情：现价{q.get('price')}元，涨跌{q.get('change_pct')}%，"
            f"换手{q.get('turnover_pct')}%，成交额{round((q.get('amount_wan') or 0)/1e4, 2)}亿，"
            f"总市值{q.get('mcap_yi')}亿"
        )
        if q.get("is_stale"):
            lines.append(f"⚠️ 报价异常：{q.get('stale_reason', '可能停牌或废码')}")

    # 估值
    if v and not v.get("error"):
        lines.append(
            f"估值：PE(TTM){v.get('pe_ttm')}，PB{v.get('pb')}，"
            f"前向PE{v.get('pe_fwd')}，PEG{v.get('peg')}（{v.get('peg_verdict')}），"
            f"EPS增速{v.get('cagr_pct')}%，PE消化{v.get('digest_years')}年，"
            f"机构覆盖{v.get('analyst_count')}家"
        )

    # 资金流
    if ffm and ffm.get("points"):
        lines.append(
            f"当日资金：主力净流入{ffm.get('main_net_total_wan')}万元，"
            f"信号{ffm.get('signal')}"
        )
    elif ffm and ffm.get("note"):
        lines.append(f"当日资金：{ffm['note']}")
    w = ffd.get("windows") if isinstance(ffd, dict) else None
    if w:
        lines.append(
            f"主力资金(元)：近5日{w.get('5d')}，近20日{w.get('20d')}，"
            f"近60日{w.get('60d')}，趋势{ffd.get('trend')}（源:{ffd.get('source')}）"
        )

    # 板块
    tags = c.get("tags") if isinstance(c, dict) else None
    if tags:
        lines.append(f"所属板块/概念：{'、'.join(tags[:12])}")

    return "\n".join(lines)
