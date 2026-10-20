US_CHAPTERS = [
    {"key": "us_ch1_quote", "title": "一、行情概览"},
    {"key": "us_ch2_price_trend", "title": "二、K线与趋势"},
    {"key": "us_ch3_technical", "title": "三、技术指标"},
    {"key": "us_ch4_profile", "title": "四、公司档案与行业"},
    {"key": "us_ch5_valuation", "title": "五、估值与市场定价"},
    {"key": "us_ch6_income", "title": "六、营收与盈利趋势"},
    {"key": "us_ch7_balance", "title": "七、资产负债与偿债能力"},
    {"key": "us_ch8_cashflow", "title": "八、现金流与盈利质量"},
    {"key": "us_ch9_sec_facts", "title": "九、SEC关键事实与数据质量"},
    {"key": "us_ch10_summary", "title": "十、综合评估"},
]
US_CHAPTER_KEYS = [item["key"] for item in US_CHAPTERS]
US_CHAPTER_TITLES = {item["key"]: item["title"] for item in US_CHAPTERS}
US_COMMENT_CHAPTER_KEYS = US_CHAPTER_KEYS[:-1]


def initial_us_chapter_states() -> list[dict]:
    return [{**item, "state": "pending"} for item in US_CHAPTERS]
