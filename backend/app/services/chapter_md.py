"""全维度报告确定性 Markdown 拼装。"""
from datetime import datetime

from app.services.chapters import CHAPTERS


def _value(value, digits=2):
    if value in (None, "", "--"):
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _money(value, unit="亿"):
    if value in (None, ""):
        return "—"
    try:
        divisor = 1e8 if unit == "亿" else 1e4
        return f"{float(value) / divisor:.2f}{unit}"
    except (TypeError, ValueError):
        return "—"


def _escape(value):
    return _value(value).replace("|", "｜").replace("\n", " ")


def _table(headers, rows):
    if not rows:
        return "> 数据未获取或当前无相关记录。"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_escape(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def _mark_pct(value):
    if value in (None, ""):
        return "—"
    try:
        number = float(value)
        marker = "🔴" if number > 0 else "🟢" if number < 0 else ""
        return f"{marker}{number:.2f}%"
    except (TypeError, ValueError):
        return _value(value)


def _ch1(data):
    q = data.get("quote") or {}
    amount = (q.get("amount_wan") or 0) / 1e4 if q.get("amount_wan") is not None else None
    rows = [
        ("最新价", f"{_value(q.get('price'))} 元（{_mark_pct(q.get('change_pct'))}）"),
        ("今开 / 昨收", f"{_value(q.get('open'))} / {_value(q.get('last_close'))}"),
        ("最高 / 最低", f"{_value(q.get('high'))} / {_value(q.get('low'))}"),
        ("换手率", f"{_value(q.get('turnover_pct'))}%"),
        ("成交额", f"{_value(amount)} 亿" if amount is not None else "—"),
        ("PE(TTM) / PE(静态)", f"{_value(q.get('pe_ttm'))} / {_value(q.get('pe_static'))}"),
        ("PB", _value(q.get("pb"))),
        ("总市值 / 流通市值", f"{_value(q.get('mcap_yi'))}亿 / {_value(q.get('float_mcap_yi'))}亿"),
        ("量比", _value(q.get("vol_ratio"))),
        ("振幅", f"{_value(q.get('amplitude_pct'))}%"),
        ("涨停 / 跌停", f"{_value(q.get('limit_up'))} / {_value(q.get('limit_down'))}"),
    ]
    board_rows = [(row.get("name"), row.get("code"), _mark_pct(row.get("change_pct")), row.get("lead_stock"))
                  for row in data.get("boards") or []]
    return "### 行情快照\n\n" + _table(["指标", "数值"], rows) + \
        "\n\n### 核心板块表现\n\n" + _table(["板块", "BK码", "涨跌", "领涨股"], board_rows)


def _ch2(data):
    p = data.get("profile") or {}
    profile = _table(["指标", "数值"], [
        ("股票名称", p.get("name")), ("所属行业", p.get("industry")),
        ("上市日期", p.get("list_date")), ("总股本", _money(p.get("total_shares"))),
        ("流通股本", _money(p.get("float_shares"))),
    ])
    boards = _table(["板块", "BK码", "当日涨跌", "领涨股"], [
        (row.get("name"), row.get("code"), _mark_pct(row.get("change_pct")), row.get("lead_stock"))
        for row in data.get("boards") or []
    ])
    evidence = data.get("evidence") or {}
    clues = [(row.get("date"), "研报", row.get("title")) for row in evidence.get("reports") or []]
    clues += [(row.get("date"), "公告", row.get("title")) for row in evidence.get("announcements") or []]
    return ("### 公司与行业\n\n" + profile +
            "\n\n### 概念板块\n\n" + boards +
            "\n\n### 业务定位证据\n\n" + _table(["日期", "来源", "条目"], clues) +
            "\n\n> 业务板块、产品、下游和壁垒仅可依据以上公开证据归纳；证据不足处标为“数据未获取”。")


def _ch3(data):
    valuation = data.get("valuation") or {}
    eps = data.get("eps") or {}
    value_rows = [
        ("PE(TTM)", valuation.get("pe_ttm")), ("PB", valuation.get("pb")),
        ("前向 PE", valuation.get("pe_fwd")), ("EPS 增速", f"{_value(valuation.get('cagr_pct'))}%"),
        ("PEG", valuation.get("peg")), ("PEG 评价", valuation.get("peg_verdict")),
        ("PE 消化年限", f"{_value(valuation.get('digest_years'))} 年"),
        ("机构覆盖", f"{valuation.get('analyst_count') or 0} 家"),
    ]
    eps_rows = [(row.get("year"), row.get("analyst_count"), row.get("eps_min"),
                 row.get("eps_mean"), row.get("eps_max")) for row in eps.get("years") or []]
    forecast_rows = [(row.get("date"), row.get("org"), row.get("eps_cur"), row.get("eps_next"),
                      row.get("eps_next2"), row.get("rating"))
                     for row in data.get("institution_forecasts") or []]
    quarter = data.get("latest_quarter") or {}
    return ("### 估值指标\n\n" + _table(["指标", "数值"], value_rows) +
            "\n\n### 一致预期 EPS\n\n" + _table(["年度", "机构数", "最小值", "均值", "最大值"], eps_rows) +
            "\n\n### 机构盈利预测明细\n\n" + _table(["日期", "机构", "当年E", "次年E", "后年E", "评级"], forecast_rows) +
            "\n\n### 最新季报与全年估算\n\n" + _table(["报告期", "营收", "归母净利", "EPS"], [
                (quarter.get("date"), _money(quarter.get("revenue")), _money(quarter.get("net_profit")), quarter.get("eps"))
            ] if quarter else []))


def _ch4(data):
    income = _table(["报告期", "营收", "营收同比", "归母净利", "净利同比", "净利率"], [
        (row.get("date"), _money(row.get("revenue")), f"{_value(row.get('revenue_yoy'))}%",
         _money(row.get("net_profit")), f"{_value(row.get('net_profit_yoy'))}%",
         f"{_value(row.get('net_margin_pct'))}%") for row in data.get("income") or []
    ])
    b = data.get("balance") or {}
    balance = _table(["指标", "数值"], [
        ("货币资金", _money(b.get("cash"))), ("存货", _money(b.get("inventory"))),
        ("流动资产", _money(b.get("current_assets"))), ("总资产", _money(b.get("total_assets"))),
        ("短期借款", _money(b.get("short_borrowings"))), ("流动负债", _money(b.get("current_liabilities"))),
        ("负债合计", _money(b.get("total_liabilities"))), ("归母股东权益", _money(b.get("equity"))),
        ("资产负债率", f"{_value(b.get('debt_ratio_pct'))}%"),
    ] if b else [])
    c = data.get("cashflow") or {}
    cash = _table(["指标", "数值"], [
        ("经营现金流净额", _money(c.get("operating"))), ("投资现金流净额", _money(c.get("investing"))),
        ("筹资现金流净额", _money(c.get("financing"))), ("现金净增加额", _money(c.get("cash_change"))),
    ] if c else [])
    a = data.get("annual") or {}
    annual = _table(["报告期", "营收", "归母净利", "净利率", "EPS"], [
        (a.get("date"), _money(a.get("revenue")), _money(a.get("net_profit")),
         f"{_value(a.get('net_margin_pct'))}%", a.get("eps"))
    ] if a else [])
    return f"### 利润表（近6期）\n\n{income}\n\n### 资产负债表\n\n{balance}\n\n### 现金流量表\n\n{cash}\n\n### 上一完整财年\n\n{annual}"


def _ch5(data):
    sections = [
        ("股东户数", ["日期", "股东户数", "环比", "户均持股"],
         [(r.get("date"), r.get("holder_num"), f"{_value(r.get('change_ratio'))}%", r.get("avg_shares")) for r in data.get("holders") or []]),
        ("融资融券（近10日）", ["日期", "融资余额", "融资买入", "融券余额"],
         [(r.get("date"), _money(r.get("rzye")), _money(r.get("rzmre")), _money(r.get("rqye"), "万")) for r in data.get("margin") or []]),
        ("大宗交易", ["日期", "成交价", "溢价率", "成交额", "买方", "卖方"],
         [(r.get("date"), r.get("price"), f"{_value(r.get('premium_pct'))}%", _money(r.get("amount")), r.get("buyer"), r.get("seller")) for r in data.get("block_trades") or []]),
        ("分红", ["除权日", "每股派息", "每10股转增", "每10股送股", "进度"],
         [(r.get("date"), r.get("bonus_rmb"), r.get("transfer_ratio"), r.get("bonus_ratio"), r.get("plan")) for r in data.get("dividends") or []]),
        ("资金流（近20日）", ["日期", "主力", "超大单", "大单"],
         [(r.get("date"), _money(r.get("main_net")), _money(r.get("super_net")), _money(r.get("large_net"))) for r in data.get("fund_flow_rows") or []]),
        ("龙虎榜（近60日）", ["日期", "上榜原因", "净买额(万)", "换手率"],
         [(r.get("date"), r.get("reason"), r.get("net_buy_wan"), f"{_value(r.get('turnover_pct'))}%") for r in data.get("dragon_tiger") or []]),
    ]
    windows = data.get("fund_flow_windows") or {}
    output = ["### 资金流汇总", "", _table(["周期", "主力净流入"], [
        ("近5日", _money(windows.get("5d"))), ("近10日", _money(windows.get("10d"))),
        ("近20日", _money(windows.get("20d"))),
    ])]
    for title, headers, rows in sections:
        output.extend(["", f"### {title}", "", _table(headers, rows)])
    return "\n".join(output)


def _ch6(data):
    m = data.get("market") or {}
    market = _table(["指标", "数值"], [
        ("交易日", m.get("date")), ("涨停家数", m.get("zt_count")), ("炸板家数", m.get("zb_count")),
        ("炸板率", f"{_value(m.get('break_rate'))}%"), ("跌停家数", m.get("dt_count")),
        ("最高连板", m.get("max_height")), ("连板梯队", m.get("ladder")),
    ])
    stocks = _table(["代码", "名称", "状态", "行业", "涨跌"], [
        (r.get("code"), r.get("name"), r.get("status"), r.get("industry"), _mark_pct(r.get("pct")))
        for r in data.get("board_stocks") or []
    ])
    return f"### 全市场情绪\n\n{market}\n\n### {data.get('industry') or '所属行业'}涨跌停个股\n\n{stocks}"


def _ch7(data):
    rows = [(r.get("date"), r.get("type"), r.get("shares"), r.get("able_shares"),
             f"{float(r.get('ratio') or 0) * 100:.2f}%") for r in data.get("upcoming") or []]
    return _table(["解禁日期", "类型", "解禁股数(万股)", "实际可流通", "占总股本"], rows)


def _ch8(data):
    intro = f"研报总数：**{data.get('total') or 0}**；评级分布：**{_value(data.get('rating_distribution'))}**。"
    rows = [(r.get("date"), r.get("org"), r.get("title"), r.get("rating")) for r in (data.get("items") or [])[:10]]
    return intro + "\n\n" + _table(["日期", "机构", "标题", "评级"], rows)


def _ch9(data):
    return _table(["日期", "类型", "标题"], [
        (r.get("date"), r.get("type"), r.get("title")) for r in data.get("items") or []
    ])


def _appx_a(data):
    intro = f"来源：{data.get('source') or '—'}；回复率：{_value(data.get('answered_ratio'))}%。"
    rows = [(r.get("ask_time") or r.get("question_time"), str(r.get("question") or "")[:100],
             "已回复" if r.get("answer") else "未回复", str(r.get("answer") or "")[:120])
            for r in data.get("items") or []]
    return intro + "\n\n" + _table(["日期", "提问摘要", "状态", "回复摘要"], rows)


def _appx_b(data):
    item = data.get("ths_item") or {}
    em = data.get("em_item") or {}
    summary = _table(["指标", "数值"], [
        ("同花顺热榜排名", item.get("rank")), ("热度值", item.get("heat")),
        ("排名变化", item.get("rank_chg")), ("东财人气排名", em.get("rank")),
        ("东财排名变化", em.get("rank_chg")), ("概念标签", "、".join(item.get("concepts") or [])),
    ])
    concepts = _table(["热门概念", "BK码", "命中热度"], [
        (r.get("concept"), r.get("bk"), r.get("hit")) for r in data.get("concepts") or []
    ])
    return f"### 个股热度\n\n{summary}\n\n### 热门概念命中\n\n{concepts}"


def _ch10(snapshot):
    valuation = ((snapshot.get("chapters") or {}).get("ch3_valuation") or {}).get("valuation") or {}
    price = valuation.get("price")
    eps = valuation.get("eps_cur")
    growth = valuation.get("cagr_pct")
    scenarios = []
    for label, factor in (("保守", 0.9), ("一致预期", 1.0), ("乐观", 1.1)):
        scenario_eps = float(eps) * factor if eps else None
        pe = float(price) / scenario_eps if price and scenario_eps else None
        scenario_growth = float(growth) * factor if growth is not None else None
        peg = pe / scenario_growth if pe and scenario_growth and scenario_growth > 0 else None
        scenarios.append((label, _value(scenario_eps), _value(pe),
                          f"{_value(scenario_growth)}%", _value(peg)))
    return "### PEG / 估值情景校验\n\n" + _table(
        ["情景", "EPS口径", "前向PE", "增速", "PEG"], scenarios
    )


_RENDERERS = {
    "ch1_quote": _ch1, "ch2_track": _ch2, "ch3_valuation": _ch3,
    "ch4_finance": _ch4, "ch5_chips": _ch5, "ch6_sentiment": _ch6,
    "ch7_unlock": _ch7, "ch8_research": _ch8, "ch9_notice": _ch9,
    "appx_a_interaction": _appx_a, "appx_b_hot": _appx_b,
}


def render_chapter_data(key: str, snapshot: dict) -> str:
    if key == "ch10_summary":
        return _ch10(snapshot)
    renderer = _RENDERERS.get(key)
    if renderer is None:
        raise ValueError(f"未知章节: {key}")
    return renderer((snapshot.get("chapters") or {}).get(key) or {})


def extract_key_facts(snapshot: dict, chapter_comments: dict[str, str]) -> str:
    q = ((snapshot.get("chapters") or {}).get("ch1_quote") or {}).get("quote") or {}
    valuation = ((snapshot.get("chapters") or {}).get("ch3_valuation") or {}).get("valuation") or {}
    finance = (snapshot.get("chapters") or {}).get("ch4_finance") or {}
    sentiment = ((snapshot.get("chapters") or {}).get("ch6_sentiment") or {}).get("market") or {}
    unlock = ((snapshot.get("chapters") or {}).get("ch7_unlock") or {}).get("upcoming") or []
    lines = [
        f"股票：{snapshot.get('name')}（{snapshot.get('code')}）",
        f"现价/涨跌：{q.get('price')} / {q.get('change_pct')}%",
        f"估值：PE(TTM)={valuation.get('pe_ttm')}，前向PE={valuation.get('pe_fwd')}，PEG={valuation.get('peg')}，PB={valuation.get('pb')}",
        f"盈利：{(finance.get('latest_quarter') or {}).get('date')} 归母净利={_money((finance.get('latest_quarter') or {}).get('net_profit'))}",
        f"情绪：涨停{sentiment.get('zt_count')}，炸板率{sentiment.get('break_rate')}%，最高连板{sentiment.get('max_height')}",
        f"未来180天解禁批次：{len(unlock)}",
    ]
    for key, comment in chapter_comments.items():
        if key != "ch10_summary" and comment:
            lines.append(f"{key}点评：{comment[:220]}")
    return "\n".join(lines)


def assemble_report(snapshot: dict, chapter_results: dict[str, dict], meta: dict) -> str:
    generated = meta.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {snapshot.get('name')}-{snapshot.get('code')} 全维度分析",
        "",
        f"> 生成时间：{generated} | 数据来源：A股全栈数据工具包与公开市场数据",
        "",
        "---",
    ]
    for chapter in CHAPTERS:
        result = chapter_results.get(chapter["key"]) or {}
        lines.extend(["", f"## {chapter['title']}", "", result.get("data_md") or "> 数据未获取。"])
        if result.get("comment_md"):
            lines.extend(["", result["comment_md"]])
    lines.extend(["", "---", "", f"> 本报告由公开数据与 AI 辅助生成 | {generated[:10]} | 不构成投资建议"])
    return "\n".join(lines).strip() + "\n"
