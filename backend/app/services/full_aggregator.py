"""十二章全维度数据聚合器。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from app.datasources.cninfo import cninfo_announcements, investor_interaction
from app.datasources.eastmoney import concept_blocks, fund_flow_minute
from app.datasources.eastmoney_ext import (
    block_trade,
    board_quotes,
    dividend_history,
    dragon_tiger_records,
    eastmoney_reports,
    eastmoney_stock_info,
    em_hot_concept,
    em_hot_rank,
    holder_num_change,
    limit_up_sentiment,
    lockup_expiry,
    margin_trading,
    stock_fund_flow_120d,
)
from app.datasources.sina import fund_flow_backup
from app.datasources.sina_finance import build_financial_summary
from app.datasources.tencent import tencent_quote
from app.datasources.ths import ths_eps_forecast, ths_hot_list
from app.services.valuation import valuation_from_inputs


def _window_sums(rows: list[dict]) -> dict:
    def total(days: int) -> float:
        return round(sum(float(row.get("main_net") or 0) for row in rows[-days:]), 0)
    return {"5d": total(5), "10d": total(10), "20d": total(20), "total_days": len(rows)}


def _safe_call(name: str, fn: Callable, *args, **kwargs) -> tuple[str, object, Optional[str]]:
    try:
        value = fn(*args, **kwargs)
        if isinstance(value, dict) and (value.get("error") or value.get("available") is False):
            message = value.get("error") or value.get("note") or f"{fn.__name__} 暂不可用"
            return name, value, message
        return name, value, None
    except Exception as exc:
        return name, None, f"{fn.__name__} 失败: {exc}"


def build_full_snapshot(code: str, on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """聚合十二章所需数据。单源失败不会拖垮整份报告。"""
    today = datetime.now().strftime("%Y-%m-%d")
    jobs = {
        "quote": (tencent_quote, [code]),
        "eps": (ths_eps_forecast, code),
        "fund_flow_minute": (fund_flow_minute, code),
        "fund_flow_rows": (stock_fund_flow_120d, code),
        "concept": (concept_blocks, code),
        "profile": (eastmoney_stock_info, code),
        "finance": (build_financial_summary, code),
        "holders": (holder_num_change, code, 8),
        "margin": (margin_trading, code, 10),
        "block_trades": (block_trade, code, 20),
        "dividends": (dividend_history, code, 5),
        "dragon_tiger": (dragon_tiger_records, code, today, 60),
        "unlock": (lockup_expiry, code, today, 180),
        "reports": (eastmoney_reports, code, 1),
        "announcements": (cninfo_announcements, code, 30),
        "sentiment": (limit_up_sentiment, ""),
        "interaction": (investor_interaction, code, 15),
        "ths_hot": (ths_hot_list, "hour"),
        "em_hot_rank": (em_hot_rank, 100),
        "em_hot_concept": (em_hot_concept, code),
    }
    results, source_errors = {}, {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(_safe_call, name, fn, *args): name
            for name, (fn, *args) in jobs.items()
        }
        completed = 0
        for future in as_completed(futures):
            name, value, error = future.result()
            completed += 1
            if error:
                source_errors[name] = error
            else:
                results[name] = value
            if on_progress:
                on_progress({
                    "status": "aggregating",
                    "current_chapter": f"数据源：{name}",
                    "progress": {"done": 0, "total": 12},
                })

    quote_map = results.get("quote") or {}
    quote = quote_map.get(code) if isinstance(quote_map, dict) else {}
    quote = quote or {}
    eps = results.get("eps") or {}
    valuation = valuation_from_inputs(code, quote, eps)
    profile = dict(results.get("profile") or {})
    report_items = ((results.get("reports") or {}).get("items") or [])
    profile.setdefault("code", code)
    profile.setdefault("name", quote.get("name") or code)
    if not profile.get("industry"):
        profile["industry"] = next((row.get("industry") for row in report_items if row.get("industry")), "")
    name = profile.get("name") or quote.get("name") or code
    concept = results.get("concept") or {}
    boards = (concept.get("boards") or [])[:12] if isinstance(concept, dict) else []

    board_data = []
    try:
        board_data = board_quotes(tuple(board.get("code") or "" for board in boards))
    except Exception as exc:
        source_errors["board_quotes"] = f"board_quotes 失败: {exc}"
    board_by_code = {row.get("code"): row for row in board_data}
    normalized_boards = [{**board, **board_by_code.get(board.get("code"), {})} for board in boards]

    finance = results.get("finance") or {}
    fund_rows = (results.get("fund_flow_rows") or [])[-20:]
    fund_source = "eastmoney"
    if not fund_rows:
        try:
            backup = fund_flow_backup(code, days=20)
            fund_rows = [{"date": row.get("date"), "main_net": row.get("net_amount") or 0}
                         for row in backup][-20:]
            if fund_rows:
                fund_source = "sina_backup"
            else:
                # 新浪备用源内部吞异常返回 []，空结果不能标成备用成功
                source_errors["fund_flow_rows_backup"] = "fund_flow_backup 无数据（东财与新浪均未取到资金流）"
                fund_source = "none"
        except Exception as exc:
            source_errors["fund_flow_rows_backup"] = f"fund_flow_backup 失败: {exc}"
            fund_source = "none"
    windows = _window_sums(fund_rows)
    sentiment = results.get("sentiment") or {}
    industry = profile.get("industry") or ""
    same_industry = [
        {"code": row.get("code"), "name": row.get("name"), "status": status,
         "industry": row.get("industry"), "pct": row.get("pct")}
        for status, pool_key in (("涨停", "zt_pool"), ("炸板", "zb_pool"), ("跌停", "dt_pool"))
        for row in sentiment.get(pool_key, [])
        if industry and row.get("industry") == industry
    ]
    reports = results.get("reports") or {"total": 0, "rating_distribution": {}, "items": []}
    announcements = results.get("announcements") or []
    ths_hot_rows = results.get("ths_hot") or []
    em_hot_rows = results.get("em_hot_rank") or []

    chapters = {
        "ch1_quote": {"quote": quote, "boards": normalized_boards[:6]},
        "ch2_track": {
            "profile": profile,
            "concept_tags": (concept.get("tags") or [])[:12] if isinstance(concept, dict) else [],
            "boards": normalized_boards,
            "evidence": {
                "reports": (reports.get("items") or [])[:5],
                "announcements": announcements[:8],
            },
        },
        "ch3_valuation": {
            "valuation": valuation or {},
            "eps": results.get("eps") or {},
            "institution_forecasts": (reports.get("items") or [])[:10],
            "latest_quarter": finance.get("latest_quarter") or {},
        },
        "ch4_finance": finance,
        "ch5_chips": {
            "holders": (results.get("holders") or [])[:8],
            "margin": (results.get("margin") or [])[:10],
            "block_trades": (results.get("block_trades") or [])[:20],
            "dividends": (results.get("dividends") or [])[:5],
            "fund_flow_minute": results.get("fund_flow_minute") or {},
            "fund_flow_rows": fund_rows,
            "fund_flow_windows": windows,
            "fund_flow_source": fund_source,
            "dragon_tiger": (results.get("dragon_tiger") or [])[:10],
        },
        "ch6_sentiment": {
            "market": {key: value for key, value in sentiment.items() if not key.endswith("_pool")},
            "board_stocks": same_industry[:30],
            "industry": industry,
        },
        "ch7_unlock": results.get("unlock") or {"history": [], "upcoming": []},
        "ch8_research": reports,
        "ch9_notice": {"items": announcements[:30]},
        "ch10_summary": {},
        "appx_a_interaction": results.get("interaction") or {"items": []},
        "appx_b_hot": {
            "ths_item": next((row for row in ths_hot_rows if str(row.get("code")) == code), None),
            "ths_top": ths_hot_rows[:10],
            "em_item": next((row for row in em_hot_rows if str(row.get("code")) == code), None),
            "concepts": results.get("em_hot_concept") or [],
        },
    }

    source_to_chapters = {
        "quote": ("ch1_quote", "ch3_valuation"),
        "eps": ("ch3_valuation",), "profile": ("ch2_track",), "concept": ("ch2_track", "ch6_sentiment"),
        "board_quotes": ("ch1_quote", "ch2_track"), "finance": ("ch3_valuation", "ch4_finance"),
        "holders": ("ch5_chips",), "margin": ("ch5_chips",), "block_trades": ("ch5_chips",),
        "dividends": ("ch5_chips",), "fund_flow_minute": ("ch5_chips",),
        "fund_flow_rows": ("ch5_chips",), "fund_flow_rows_backup": ("ch5_chips",),
        "dragon_tiger": ("ch5_chips",), "sentiment": ("ch6_sentiment",),
        "unlock": ("ch7_unlock",), "reports": ("ch2_track", "ch3_valuation", "ch8_research"),
        "announcements": ("ch2_track", "ch9_notice"), "interaction": ("appx_a_interaction",),
        "ths_hot": ("appx_b_hot",), "em_hot_rank": ("appx_b_hot",),
        "em_hot_concept": ("appx_b_hot",),
    }
    chapter_errors = {}
    for source, message in source_errors.items():
        for chapter in source_to_chapters.get(source, (source,)):
            chapter_errors.setdefault(chapter, []).append(message)

    return {
        "code": code,
        "name": name,
        "chapters": chapters,
        "errors": chapter_errors,
        "source_errors": source_errors,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
