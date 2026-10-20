from app.core.instrument import parse_us_instrument
from app.services import us_aggregator


def test_aggregator_partial_success_and_sec_skipped(monkeypatch):
    calls = {"sina": 0}

    def fake_sina(instrument):
        calls["sina"] += 1
        return {"symbol": instrument.symbol, "name": "Apple", "price": 100.0, "currency": "USD", "sources": []}

    def fake_tencent(instrument):
        raise RuntimeError("failed")

    def fake_yahoo(symbol):
        return {"symbol": symbol, "bars": [{"date": "2026-10-01", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 1}], "currency": "USD", "sources": []}

    def fake_yahoo_summary(instrument):
        return {"profile": {"name": "Apple Inc.", "industry": "Consumer Electronics", "sector": "Technology"},
                "valuation": {"pe_ttm": 25.0}, "financials": {"income": [{"TotalRevenue": 1000}], "balance": [], "cashflow": []}, "sources": []}

    def fake_em(instrument):
        raise RuntimeError("failed")

    monkeypatch.setattr(us_aggregator, "fetch_sina_quote", fake_sina)
    monkeypatch.setattr(us_aggregator, "fetch_tencent_quote", fake_tencent)
    monkeypatch.setattr(us_aggregator, "fetch_yahoo_chart", fake_yahoo)
    monkeypatch.setattr(us_aggregator, "fetch_yahoo_summary", fake_yahoo_summary)
    monkeypatch.setattr(us_aggregator, "fetch_us_fundamentals", fake_em)
    snapshot = us_aggregator.build_us_snapshot(parse_us_instrument("AAPL"), sec_contact="")
    assert snapshot["market"] == "US"
    assert snapshot["code"] == "AAPL"
    assert len(snapshot["chapters"]) == 10
    assert snapshot["source_errors"]["sec"].startswith("未配置 SEC_CONTACT")
    assert snapshot["source_errors"]["tencent_quote"] == "failed"
    assert snapshot["chapters"]["us_ch9_sec_facts"]["source_errors"]["sec"].startswith("未配置 SEC_CONTACT")


def test_aggregator_fails_when_core_sources_missing(monkeypatch):
    def fail(*args):
        raise RuntimeError("failed")
    monkeypatch.setattr(us_aggregator, "fetch_sina_quote", fail)
    monkeypatch.setattr(us_aggregator, "fetch_tencent_quote", fail)
    monkeypatch.setattr(us_aggregator, "fetch_yahoo_chart", fail)
    monkeypatch.setattr(us_aggregator, "fetch_us_daily_history", fail)
    try:
        us_aggregator.build_us_snapshot(parse_us_instrument("AAPL"), sec_contact="")
    except RuntimeError:
        return
    raise AssertionError("缺少行情和K线时不应成功")
