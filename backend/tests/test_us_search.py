import json
from types import SimpleNamespace
from urllib.parse import quote

from app.datasources.us import search


def _search(monkeypatch, rows, query="英伟达", limit=10):
    payload = {"QuotationCodeTable": {"Data": rows}}

    def fake_run(command, **kwargs):
        assert command[:2] == ["curl", "-s"]
        assert f"input={quote(query)}" in command[2]
        assert kwargs == {"capture_output": True, "text": True, "timeout": 15}
        return SimpleNamespace(stdout=json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(search.subprocess, "run", fake_run)
    return search.search_us_stocks.__wrapped__(query, limit)


def test_search_keeps_current_us_stock_and_excludes_etf(monkeypatch):
    rows = [
        {
            "Code": "NVDA",
            "Name": "英伟达",
            "MktNum": "105",
            "Classify": "UsStock",
            "SecurityType": "7",
            "SecurityTypeName": "美股",
            "TypeUS": "1",
        },
        {
            "Code": "NVDL",
            "Name": "二倍做多英伟达ETF-GraniteShares",
            "MktNum": "105",
            "Classify": "UsStock",
            "SecurityType": "7",
            "SecurityTypeName": "美股",
            "TypeUS": "5",
        },
    ]

    result = _search(monkeypatch, rows)

    assert result["query"] == "英伟达"
    assert result["items"] == [{
        "symbol": "NVDA",
        "name": "英伟达",
        "exchange": "NASDAQ",
        "asset_type": "stock",
        "market": "US",
    }]


def test_search_maps_us_markets_and_ignores_security_type_value(monkeypatch):
    rows = [
        {
            "Code": "NVDA",
            "Name": "英伟达",
            "MktNum": 105,
            "Classify": "UsStock",
            "SecurityType": "7",
            "TypeUS": 1,
        },
        {
            "Code": "IBM",
            "Name": "IBM",
            "MktNum": "106",
            "Classify": "UsStock",
            "SecurityType": "20",
            "TypeUS": "1",
        },
        {
            "Code": "TEST",
            "Name": "Test Company",
            "MktNum": "107",
            "Classify": "UsStock",
            "SecurityType": "99",
            "TypeUS": "1",
        },
    ]

    result = _search(monkeypatch, rows, query="stock")

    assert [(item["symbol"], item["exchange"]) for item in result["items"]] == [
        ("NVDA", "NASDAQ"),
        ("IBM", "NYSE"),
        ("TEST", "US_OTHER"),
    ]


def test_search_rejects_non_stock_and_incomplete_rows(monkeypatch):
    rows = [
        None,
        "invalid",
        {"Code": "CN", "Name": "非美股", "MktNum": "1", "Classify": "UsStock", "TypeUS": "1"},
        {"Code": "ETF", "Name": "ETF", "MktNum": "105", "Classify": "UsStock", "TypeUS": "5"},
        {"Code": "INDEX", "Name": "指数", "MktNum": "105", "Classify": "Index", "TypeUS": "1"},
        {"Code": "NOCLASS", "Name": "缺分类", "MktNum": "105", "TypeUS": "1"},
        {"Code": "NOTYPE", "Name": "缺类型", "MktNum": "105", "Classify": "UsStock"},
        {"Name": "缺代码", "MktNum": "105", "Classify": "UsStock", "TypeUS": "1"},
        {"Code": "NONAME", "MktNum": "105", "Classify": "UsStock", "TypeUS": "1"},
    ]

    result = _search(monkeypatch, rows, query="invalid")

    assert result["items"] == []
