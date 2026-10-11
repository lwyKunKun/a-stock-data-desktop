"""新浪财报三表数据源。"""
from concurrent.futures import ThreadPoolExecutor
import re

import requests

from app.core.cache import cached
from app.core.em_client import UA
from app.core.ticker import get_prefix, norm_ticker

_FINANCE_URL = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"


@cached("sina_finance", until_eod=True)
def sina_financial_report(code: str, report_type: str = "lrb", num: int = 8) -> list[dict]:
    """返回新浪利润表(lrb)、资产负债表(fzb)或现金流量表(llb)。"""
    code = norm_ticker(code, stock_only=True)
    if report_type not in {"lrb", "fzb", "llb"}:
        raise ValueError("report_type 须为 lrb/fzb/llb")
    response = requests.get(
        _FINANCE_URL,
        params={
            "paperCode": f"{get_prefix(code)}{code}",
            "source": report_type,
            "type": "0",
            "page": "1",
            "num": str(num),
        },
        headers={"User-Agent": UA},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json() or {}
    result = payload.get("result") or {}
    data = result.get("data") or {}
    report_list = data.get("report_list")
    if report_list is None:
        raise RuntimeError("新浪财报返回结构缺少 result.data.report_list")
    if not isinstance(report_list, dict):
        raise RuntimeError("新浪财报 report_list 不是对象")

    rows = []
    for period in sorted(report_list, reverse=True)[:num]:
        obj = report_list[period] or {}
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for item in obj.get("data") or []:
            title = item.get("item_title") or ""
            if not title or item.get("item_value") is None:
                continue
            rec[title] = item.get("item_value")
            yoy = item.get("item_tongbi")
            if yoy not in (None, ""):
                rec[f"{title}_同比"] = yoy
        rows.append(rec)
    return rows


def _number(value):
    if value in (None, "", "--", "-"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier, text = 1e8, text[:-1]
    elif text.endswith("万"):
        multiplier, text = 1e4, text[:-1]
    text = re.sub(r"[^0-9.+-]", "", text)
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _pick(row: dict, aliases: tuple[str, ...]):
    for alias in aliases:
        if alias in row:
            return _number(row[alias])
    for title, value in row.items():
        if any(alias in title for alias in aliases):
            return _number(value)
    return None


def _pick_yoy(row: dict, aliases: tuple[str, ...]):
    return _pick(row, tuple(f"{alias}_同比" for alias in aliases))


def _income_row(row: dict) -> dict:
    revenue_aliases = ("营业总收入", "营业收入", "主营业务收入")
    profit_aliases = ("归属于母公司所有者的净利润", "归属于上市公司股东的净利润", "归母净利润")
    revenue = _pick(row, revenue_aliases)
    net_profit = _pick(row, profit_aliases)
    return {
        "date": row.get("报告期", ""),
        "revenue": revenue,
        "revenue_yoy": _pick_yoy(row, revenue_aliases),
        "net_profit": net_profit,
        "net_profit_yoy": _pick_yoy(row, profit_aliases),
        "net_margin_pct": round(net_profit / revenue * 100, 2) if revenue and net_profit is not None else None,
        "eps": _pick(row, ("基本每股收益", "每股收益")),
    }


def _balance_row(row: dict) -> dict:
    total_assets = _pick(row, ("资产总计", "总资产"))
    total_liabilities = _pick(row, ("负债合计", "总负债"))
    return {
        "date": row.get("报告期", ""),
        "cash": _pick(row, ("货币资金",)),
        "inventory": _pick(row, ("存货",)),
        "current_assets": _pick(row, ("流动资产合计",)),
        "total_assets": total_assets,
        "short_borrowings": _pick(row, ("短期借款",)),
        "current_liabilities": _pick(row, ("流动负债合计",)),
        "total_liabilities": total_liabilities,
        "equity": _pick(row, ("归属于母公司股东权益合计", "归属于母公司所有者权益合计", "股东权益合计")),
        "debt_ratio_pct": round(total_liabilities / total_assets * 100, 2)
        if total_assets and total_liabilities is not None else None,
    }


def _cashflow_row(row: dict) -> dict:
    return {
        "date": row.get("报告期", ""),
        "operating": _pick(row, ("经营活动产生的现金流量净额",)),
        "investing": _pick(row, ("投资活动产生的现金流量净额",)),
        "financing": _pick(row, ("筹资活动产生的现金流量净额",)),
        "cash_change": _pick(row, ("现金及现金等价物净增加额", "现金净增加额")),
    }


def build_financial_summary(code: str) -> dict:
    """并发拉三张报表并归一化为报告所需字段。"""
    with ThreadPoolExecutor(max_workers=3) as pool:
        income_future = pool.submit(sina_financial_report, code, "lrb", 8)
        balance_future = pool.submit(sina_financial_report, code, "fzb", 2)
        cashflow_future = pool.submit(sina_financial_report, code, "llb", 2)
    income = [_income_row(row) for row in income_future.result()]
    balances = balance_future.result()
    cashflows = cashflow_future.result()
    annual = next((row for row in income if row["date"].endswith("12-31")), None)
    return {
        "income": income[:6],
        "balance": _balance_row(balances[0]) if balances else {},
        "cashflow": _cashflow_row(cashflows[0]) if cashflows else {},
        "annual": annual or {},
        "latest_quarter": income[0] if income else {},
    }
