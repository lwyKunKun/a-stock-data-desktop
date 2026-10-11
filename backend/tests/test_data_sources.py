import json

import pytest

from app.datasources import cninfo, eastmoney_ext, sina_finance


class FakeResponse:
    def __init__(self, payload, status_code=200, content=None):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = json.dumps(payload, ensure_ascii=False)
        self.content = content if content is not None else self.text.encode()

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_sina_financial_report_and_summary(monkeypatch):
    payloads = {
        "lrb": {
            "result": {"data": {"report_list": {
                "20260630": {"data": [
                    {"item_title": "营业总收入", "item_value": "1000000000", "item_tongbi": "12.5"},
                    {"item_title": "归属于母公司所有者的净利润", "item_value": "200000000", "item_tongbi": "20"},
                    {"item_title": "基本每股收益", "item_value": "1.23", "item_tongbi": ""},
                ]},
                "20251231": {"data": [
                    {"item_title": "营业总收入", "item_value": "1800000000", "item_tongbi": "8"},
                    {"item_title": "归属于母公司所有者的净利润", "item_value": "300000000", "item_tongbi": "10"},
                ]},
            }}}
        },
        "fzb": {"result": {"data": {"report_list": {"20260630": {"data": [
            {"item_title": "资产总计", "item_value": "5000000000", "item_tongbi": ""},
            {"item_title": "负债合计", "item_value": "2000000000", "item_tongbi": ""},
            {"item_title": "货币资金", "item_value": "800000000", "item_tongbi": ""},
        ]}}}}},
        "llb": {"result": {"data": {"report_list": {"20260630": {"data": [
            {"item_title": "经营活动产生的现金流量净额", "item_value": "250000000", "item_tongbi": ""},
        ]}}}}},
    }

    def fake_get(url, params, **kwargs):
        return FakeResponse(payloads[params["source"]])

    monkeypatch.setattr(sina_finance.requests, "get", fake_get)
    summary = sina_finance.build_financial_summary("600519")
    assert summary["income"][0]["revenue"] == 1_000_000_000
    assert summary["income"][0]["net_margin_pct"] == 20
    assert summary["balance"]["debt_ratio_pct"] == 40
    assert summary["cashflow"]["operating"] == 250_000_000
    assert summary["annual"]["date"] == "2025-12-31"


def test_margin_and_lockup_normalization(monkeypatch):
    def fake_datacenter(report_name, **kwargs):
        if report_name == "RPTA_WEB_RZRQ_GGMX":
            return [{"DATE": "2026-10-09 00:00:00", "RZYE": 100, "RQYE": 20}]
        if report_name == "RPT_LIFT_STAGE":
            return [{"FREE_DATE": "2026-11-01 00:00:00", "FREE_SHARES_TYPE": "定增",
                     "FREE_SHARES": 10, "ABLE_FREE_SHARES": 8, "FREE_RATIO": 0.02}]
        return []

    monkeypatch.setattr(eastmoney_ext, "eastmoney_datacenter", fake_datacenter)
    margin = eastmoney_ext.margin_trading("600519")
    lockup = eastmoney_ext.lockup_expiry("600519", "2026-10-10")
    assert margin[0]["date"] == "2026-10-09"
    assert margin[0]["rzye"] == 100
    assert lockup["upcoming"][0]["type"] == "定增"
    assert lockup["upcoming"][0]["able_shares"] == 8


def test_limit_up_sentiment_uses_latest_pool(monkeypatch):
    monkeypatch.setattr(eastmoney_ext, "em_zt_pool", lambda date: [
        {"limit_days": 2, "industry": "白酒"}, {"limit_days": 1, "industry": "元件"}
    ])
    monkeypatch.setattr(eastmoney_ext, "em_zb_pool", lambda date: [{"code": "x"}])
    monkeypatch.setattr(eastmoney_ext, "em_dt_pool", lambda date: [{"code": "y"}])
    result = eastmoney_ext.limit_up_sentiment("20261009")
    assert result["zt_count"] == 2
    assert result["break_rate"] == pytest.approx(33.3)
    assert result["max_height"] == 2
    assert result["ladder"] == {1: 1, 2: 1}


def test_investor_interaction_market_routing(monkeypatch):
    monkeypatch.setattr(cninfo, "sse_e_interaction", lambda code, limit: [{"answer": "已回复"}])
    monkeypatch.setattr(cninfo, "cninfo_irm", lambda code, limit: [{"answer": None}])
    sh = cninfo.investor_interaction("600519")
    sz = cninfo.investor_interaction("002594")
    bj = cninfo.investor_interaction("920982")
    assert sh["source"] == "sse_e" and sh["answered_ratio"] == 100
    assert sz["source"] == "cninfo_irm" and sz["answered_ratio"] == 0
    assert bj["available"] is False
