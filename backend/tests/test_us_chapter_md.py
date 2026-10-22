from app.services import us_chapter_md
from app.services.us_field_labels import US_FIELD_LABELS


SNAPSHOT = {
    "market": "US",
    "code": "AAPL",
    "name": "Apple Inc.",
    "currency": "USD",
    "chapters": {
        "us_ch1_quote": {
            "quote": {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "price": 189.5,
                "change_pct": 1.25,
                "market_cap_hundred_million": 285000,
                "pe_ttm": 28.4,
            }
        },
        "us_ch2_price_trend": {
            "latest": {"close": 189.5, "change_pct": 1.25},
            "history": {
                "bars": [
                    {
                        "date": "2026-10-21",
                        "open": 187.2,
                        "high": 190.1,
                        "low": 186.9,
                        "close": 189.5,
                        "volume": 52130000,
                        "adj_close": 189.5,
                    }
                ]
            },
        },
        "us_ch3_technical": {
            "latest": {
                "date": "2026-10-21",
                "close": 189.5,
                "ma20": 185.1,
                "macd_dif": 1.21,
                "rsi14": 58.2,
                "boll_upper": 193.4,
                "volume_avg_20d": 49200000,
            }
        },
        "us_ch4_profile": {
            "profile": {
                "name": "Apple Inc.",
                "exchange": "NasdaqGS",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "United States",
                "website": "https://www.apple.com",
                "description": "Apple designs and markets consumer electronics.",
            },
            "cik": "0000320193",
        },
        "us_ch5_valuation": {
            "valuation": {
                "market_cap": 2850000000000,
                "enterprise_value": 2900000000000,
                "pe_ttm": 28.4,
                "pe_forward": 26.1,
                "pb": 45.2,
                "ps_ttm": 7.1,
                "eps_ttm": 6.58,
                "eps_forward": 7.2,
                "dividend_yield": 0.0045,
                "revenue_growth": 0.061,
            },
            "quote": {"pe_ttm": 28.4, "pb": 45.2, "market_cap_hundred_million": 285000},
        },
        "us_ch6_income": {
            "yahoo": [
                {
                    "endDate": "2025-09-27",
                    "totalRevenue": 391035000000,
                    "netIncome": 93736000000,
                    "grossProfit": 180683000000,
                    "operatingIncome": 123216000000,
                }
            ],
            "eastmoney": [
                {
                    "REPORT_DATE": "2025-09-30",
                    "TOTAL_OPERATE_INCOME": 391035000000,
                    "PARENT_NETPROFIT": 93736000000,
                    "BASIC_EPS": 6.58,
                }
            ],
            "sec": [
                {
                    "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "unit": "USD",
                    "start": "2024-09-29",
                    "end": "2025-09-27",
                    "value": 391035000000,
                    "form": "10-K",
                    "filed": "2025-10-31",
                    "fy": 2025,
                    "fp": "FY",
                    "accn": "0000320193-25-000079",
                }
            ],
        },
        "us_ch7_balance": {
            "yahoo": [
                {
                    "endDate": "2025-09-27",
                    "totalAssets": 364980000000,
                    "totalLiab": 308030000000,
                    "stockholdersEquity": 56952000000,
                    "cashAndCashEquivalents": 29942000000,
                    "currentRatio": 0.87,
                }
            ],
            "eastmoney": [],
            "sec": [],
        },
        "us_ch8_cashflow": {
            "yahoo": [
                {
                    "endDate": "2025-09-27",
                    "operatingCashflow": 118254000000,
                    "capitalExpenditures": -12215000000,
                    "freeCashflow": 106033000000,
                }
            ],
            "eastmoney": [],
            "sec": [],
        },
        "us_ch9_sec_facts": {
            "sec": {
                "ticker": "AAPL",
                "cik": "0000320193",
                "company": "Apple Inc.",
                "available": True,
                "note": "SEC company facts retrieved successfully.",
                "metrics": {
                    "revenue": [{"value": 391035000000}],
                    "net_income": [{"value": 93736000000}],
                },
            },
            "sources": [],
            "source_errors": {"sec": "未配置 SEC_CONTACT，已跳过 SEC 官方数据；其他数据不受影响"},
        },
        "us_ch10_summary": {},
    },
    "source_errors": {"yahoo_summary": "failed"},
    "errors": {},
    "sources": [],
    "fetched_at": "2026-10-22 00:00:00",
}


def test_us_chapter_headers_are_localized_and_values_are_preserved():
    rendered_by_chapter = {
        chapter_key: us_chapter_md.render_us_chapter_data(chapter_key, SNAPSHOT)
        for chapter_key in (
            "us_ch1_quote",
            "us_ch2_price_trend",
            "us_ch3_technical",
            "us_ch4_profile",
            "us_ch5_valuation",
            "us_ch6_income",
            "us_ch7_balance",
            "us_ch8_cashflow",
            "us_ch9_sec_facts",
        )
    }

    quote_md = rendered_by_chapter["us_ch1_quote"]
    assert "| 最新价 | 189.5 |" in quote_md
    assert "| 涨跌幅 | 1.25 |" in quote_md
    assert "| 证券代码 | AAPL |" in quote_md
    assert "| 公司名称 | Apple Inc. |" in quote_md
    assert "market_cap_hundred_million" not in quote_md
    assert "change_pct" not in quote_md

    tech_md = rendered_by_chapter["us_ch3_technical"]
    assert "| MA20(20日均线) | 185.1 |" in tech_md
    assert "| RSI14 | 58.2 |" in tech_md
    assert "volume_avg_20d" not in tech_md

    profile_md = rendered_by_chapter["us_ch4_profile"]
    assert "| SEC公司标识号 | 0000320193 |" in profile_md
    assert "| CIK |" not in profile_md

    income_md = rendered_by_chapter["us_ch6_income"]
    assert "### Yahoo Finance" in income_md
    assert "### 东方财富" in income_md
    assert "### SEC官方数据" in income_md
    assert "| 截止日期 | 总营收 | 净利润 | 毛利润 | 营业利润 |" in income_md
    assert "| 2025-09-27 | 391035000000 | 93736000000 | 180683000000 | 123216000000 |" in income_md
    assert "| 报告期 | 营业总收入 | 归母净利润 | 基本每股收益 |" in income_md
    assert "| 2025-09-30 | 391035000000 | 93736000000 | 6.58 |" in income_md
    assert "| SEC指标 | 计量单位 | 期间开始日期 | 期间结束日期 | 数值 | SEC表单 | 提交日期 | 财年 |" in income_md
    assert "| RevenueFromContractWithCustomerExcludingAssessedTax | USD | 2024-09-29 | 2025-09-27 | 391035000000 | 10-K | 2025-10-31 | 2025 |" in income_md
    assert "totalRevenue" not in income_md
    assert "TOTAL_OPERATE_INCOME" not in income_md
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in income_md

    sec_md = rendered_by_chapter["us_ch9_sec_facts"]
    assert "| SEC公司标识号 | 0000320193 |" in sec_md
    assert "| 公司名称 | Apple Inc. |" in sec_md
    assert "| 数据可用 | True |" in sec_md
    assert "| SEC官方数据 | 未配置 SEC_CONTACT，已跳过 SEC 官方数据；其他数据不受影响 |" in sec_md
    assert "| 营收 | 391035000000 |" in sec_md
    assert "available" not in sec_md
    assert "| company |" not in sec_md
    assert "| cik |" not in sec_md


def test_us_chapter_unknown_fields_and_empty_data():
    snapshot = {
        "chapters": {
            "us_ch1_quote": {"quote": {"custom_unknown_field": "keep-me", "price": 10}},
            "us_ch3_technical": {"latest": {}},
        }
    }
    rendered = us_chapter_md.render_us_chapter_data("us_ch1_quote", snapshot)
    assert "| custom_unknown_field | keep-me |" in rendered
    assert "| 最新价 | 10 |" in rendered
    assert us_chapter_md.render_us_chapter_data("us_ch3_technical", snapshot) == "数据未获取。"
