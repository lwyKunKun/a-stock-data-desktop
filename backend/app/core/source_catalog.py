SOURCE_CATALOG = {
    "sina_us_quote": {
        "id": "sina_us_quote", "name": "新浪美股行情", "grade": "C",
        "restriction": "仅限个人研究，不保证持续可用，禁止商业再分发",
    },
    "tencent_us_quote": {
        "id": "tencent_us_quote", "name": "腾讯美股行情", "grade": "C",
        "restriction": "仅限个人研究，不保证持续可用，禁止商业再分发",
    },
    "eastmoney_us": {
        "id": "eastmoney_us", "name": "东方财富美股数据", "grade": "C",
        "restriction": "仅限个人研究，不保证持续可用，禁止商业再分发",
    },
    "yahoo_chart": {
        "id": "yahoo_chart", "name": "Yahoo Finance K线", "grade": "D",
        "restriction": "非官方接口，仅限个人研究，不得商业使用或再分发",
    },
    "yahoo_summary": {
        "id": "yahoo_summary", "name": "Yahoo Finance 基本面", "grade": "D",
        "restriction": "非官方接口，仅限个人研究，不得商业使用或再分发",
    },
    "sec_companyfacts": {
        "id": "sec_companyfacts", "name": "SEC EDGAR", "grade": "S",
        "restriction": "官方公开数据，须提供真实联系信息并遵守访问限速",
    },
    "local_indicators": {
        "id": "local_indicators", "name": "本地技术指标计算", "grade": "S",
        "restriction": "本地计算；原始行情仍受上游数据源条款约束",
    },
}


def source_disclosure(source_id: str, *, status: str = "ok", as_of: str = "") -> dict:
    item = dict(SOURCE_CATALOG[source_id])
    item.update({"status": status, "as_of": as_of})
    return item
