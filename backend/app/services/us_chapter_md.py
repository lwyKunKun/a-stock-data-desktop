import json

from app.services.us_chapters import US_CHAPTER_TITLES, US_CHAPTERS
from app.services.us_field_labels import label_for


def _value(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _dict_table(data: dict) -> str:
    if not data:
        return "数据未获取。"
    lines = ["| 指标 | 数值 |", "|---|---|"]
    for key, value in data.items():
        if key not in {"sources", "series"}:
            lines.append(f"| {label_for(key)} | {_value(value)} |")
    return "\n".join(lines)


def _rows_table(rows: list[dict], limit: int = 8) -> str:
    rows = [row for row in rows if isinstance(row, dict)][:limit]
    if not rows:
        return "数据未获取。"
    keys = list(dict.fromkeys(key for row in rows for key in row.keys()))[:8]
    lines = ["| " + " | ".join(label_for(key) for key in keys) + " |", "|" + "|".join("---" for _ in keys) + "|"]
    lines.extend("| " + " | ".join(_value(row.get(key)) for key in keys) + " |" for row in rows)
    return "\n".join(lines)


def render_us_chapter_data(key: str, snapshot: dict) -> str:
    chapter = (snapshot.get("chapters") or {}).get(key) or {}
    if key == "us_ch1_quote":
        return _dict_table(chapter.get("quote") or {})
    if key == "us_ch2_price_trend":
        history = chapter.get("history") or {}
        return "### 趋势摘要\n" + _dict_table(chapter.get("latest") or {}) + "\n\n### 最近K线\n" + _rows_table((history.get("bars") or [])[-10:])
    if key == "us_ch3_technical":
        return _dict_table(chapter.get("latest") or {})
    if key == "us_ch4_profile":
        return _dict_table({**(chapter.get("profile") or {}), "CIK": chapter.get("cik")})
    if key == "us_ch5_valuation":
        return _dict_table({**(chapter.get("valuation") or {}), **{k: v for k, v in (chapter.get("quote") or {}).items() if k in ("pe_ttm", "pb", "market_cap_hundred_million")}})
    if key in ("us_ch6_income", "us_ch7_balance", "us_ch8_cashflow"):
        text = []
        for source, data in chapter.items():
            text.append(f"### {label_for(source)}\n" + (_rows_table(data) if isinstance(data, list) else _dict_table(data)))
        return "\n\n".join(text)
    if key == "us_ch9_sec_facts":
        sec = chapter.get("sec") or {}
        header = _dict_table({key: sec.get(key) for key in ("cik", "company", "available", "note")})
        metrics = sec.get("metrics") or {}
        metric_rows = {}
        for metric_key, value in metrics.items():
            if not isinstance(value, list) or not value:
                continue
            latest = value[-1]
            metric_rows[metric_key] = latest.get("value") if isinstance(latest, dict) else latest
        return header + "\n\n### SEC关键事实\n" + _dict_table(metric_rows) + "\n\n### 数据源错误\n" + _dict_table(chapter.get("source_errors") or {})
    if key == "us_ch10_summary":
        return "综合评估由前九章确定性数据与点评生成。"
    return _dict_table(chapter)


def extract_us_key_facts(snapshot: dict, comments: dict[str, str]) -> str:
    facts = [f"股票：{snapshot.get('name')}（{snapshot.get('code')}）", f"币种：{snapshot.get('currency')}"]
    quote = ((snapshot.get("chapters") or {}).get("us_ch1_quote") or {}).get("quote") or {}
    technical = ((snapshot.get("chapters") or {}).get("us_ch3_technical") or {}).get("latest") or {}
    valuation = ((snapshot.get("chapters") or {}).get("us_ch5_valuation") or {}).get("valuation") or {}
    facts.extend([f"行情：{_value(quote)}", f"技术：{_value(technical)}", f"估值：{_value(valuation)}"])
    for key, comment in comments.items():
        facts.append(f"{US_CHAPTER_TITLES.get(key, key)}点评：{comment[:220]}")
    return "\n".join(facts)


def assemble_us_report(snapshot: dict, chapters: list[dict], meta: dict) -> str:
    lines = [f"# {snapshot.get('name')}（{snapshot.get('code')}）美股全维度报告", "", f"> 生成时间：{meta.get('generated_at')}　币种：{snapshot.get('currency', 'USD')}", "", "> 本报告仅供个人研究，不构成投资建议；C/D级来源不得用于商业再分发。", ""]
    for item in chapters:
        lines.extend([f"## {item['title']}", "", item.get("data_md") or "", "", item.get("comment_md") or "", ""])
    return "\n".join(lines)
