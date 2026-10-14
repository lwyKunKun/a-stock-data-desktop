from app.services import chapter_md, report_generator
from app.services.chapters import CHAPTERS


def snapshot_fixture():
    return {
        "code": "600519", "name": "贵州茅台", "errors": {}, "fetched_at": "2026-10-11 10:00:00",
        "chapters": {
            "ch1_quote": {"quote": {"name": "贵州茅台", "price": 1500, "change_pct": 1.2,
                                             "open": 1480, "last_close": 1482, "high": 1510, "low": 1470,
                                             "turnover_pct": 1, "amount_wan": 100000, "pe_ttm": 25,
                                             "pe_static": 26, "pb": 8, "mcap_yi": 19000,
                                             "float_mcap_yi": 19000, "vol_ratio": 1.1,
                                             "amplitude_pct": 2.7, "limit_up": 1630, "limit_down": 1334},
                              "boards": []},
            "ch2_track": {"profile": {"name": "贵州茅台", "industry": "白酒"},
                          "concept_tags": ["白酒"], "boards": [], "evidence": {}},
            "ch3_valuation": {"valuation": {"price": 1500, "pe_ttm": 25, "pb": 8,
                                                          "pe_fwd": 22, "cagr_pct": 15, "peg": 1.47,
                                                          "eps_cur": 68, "analyst_count": 10},
                               "eps": {"years": []}, "institution_forecasts": [], "latest_quarter": {}},
            "ch4_finance": {"income": [], "balance": {}, "cashflow": {}, "annual": {}},
            "ch5_chips": {"holders": [], "margin": [], "block_trades": [], "dividends": [],
                          "fund_flow_rows": [], "fund_flow_windows": {}, "dragon_tiger": []},
            "ch6_sentiment": {"market": {"date": "20261009", "zt_count": 50, "zb_count": 10,
                                                       "break_rate": 16.7, "dt_count": 2,
                                                       "max_height": 5, "ladder": {1: 30, 2: 10}},
                              "board_stocks": [], "industry": "白酒"},
            "ch7_unlock": {"history": [], "upcoming": []},
            "ch8_research": {"total": 0, "rating_distribution": {}, "items": []},
            "ch9_notice": {"items": []}, "ch10_summary": {},
            "appx_a_interaction": {"source": "sse_e", "answered_ratio": 0, "items": []},
            "appx_b_hot": {"ths_item": None, "em_item": None, "concepts": []},
        },
    }


def test_all_chapters_render_and_assemble():
    snapshot = snapshot_fixture()
    results = {}
    for chapter in CHAPTERS:
        data = chapter_md.render_chapter_data(chapter["key"], snapshot)
        assert isinstance(data, str) and data
        results[chapter["key"]] = {"data_md": data, "comment_md": "> 点评", "state": "ok"}
    markdown = chapter_md.assemble_report(snapshot, results, {"generated_at": "2026-10-11 10:00:00"})
    assert markdown.startswith("# 贵州茅台-600519 全维度分析")
    assert "## 十、综合评估" in markdown
    assert "## 附加B、热度" in markdown


def test_generate_report_structures_data_warnings(monkeypatch):
    snapshot = snapshot_fixture()
    detail = (
        "stock_fund_flow_120d 失败: HTTPSConnectionPool(host='push2his.eastmoney.com'): "
        "Max retries exceeded with url: /api/qt/stock/fflow/daykline/get?secid=1.600519 "
        "(Caused by RemoteDisconnected('Remote end closed connection without response'))"
    )
    snapshot["errors"] = {"ch5_chips": ["", detail]}
    monkeypatch.setattr(report_generator, "build_full_snapshot", lambda code, on_progress=None: snapshot)
    monkeypatch.setattr(
        report_generator,
        "chat",
        lambda *args, **kwargs: ("> 数据点评。", {"total_tokens": 5}),
    )

    report = report_generator.generate_report("600519")
    chapter = next(item for item in report["chapters"] if item["key"] == "ch5_chips")

    assert chapter["data_warnings"] == [detail]
    assert "部分数据源暂不可用（1 项），其余数据不受影响" in chapter["data_md"]
    assert "HTTPSConnectionPool" not in chapter["data_md"]
    assert detail not in report["full_markdown"]
    assert report["meta"]["data_errors"]["ch5_chips"] == ["", detail]


def test_generate_report_runs_summary_last(monkeypatch):
    snapshot = snapshot_fixture()
    calls = []
    monkeypatch.setattr(report_generator, "build_full_snapshot", lambda code, on_progress=None: snapshot)

    def fake_chat(system, user, **kwargs):
        calls.append(system)
        if system == report_generator.SUMMARY_SYSTEM:
            return "**定性**：中性。\n\n**核心看点**：数据有限。", {"total_tokens": 20}
        return "> 数据点评。", {"total_tokens": 5}

    monkeypatch.setattr(report_generator, "chat", fake_chat)
    progress = []
    report = report_generator.generate_report("600519", progress.append)
    assert len(report["chapters"]) == 12
    assert report["chapters"][-3]["key"] == "ch10_summary"
    assert report["meta"]["usage"]["total_tokens"] == 75
    assert calls[-1] == report_generator.SUMMARY_SYSTEM
    assert report["full_markdown"].startswith("# 贵州茅台-600519")
    assert progress[-1]["progress"] == {"done": 12, "total": 12}


def test_retry_single_chapter(monkeypatch):
    snapshot = snapshot_fixture()
    results = []
    for chapter in CHAPTERS:
        results.append({"key": chapter["key"], "title": chapter["title"],
                        "data_md": chapter_md.render_chapter_data(chapter["key"], snapshot),
                        "comment_md": "> 旧点评", "state": "comment_failed", "usage": {}})
    results[0]["data_warnings"] = ["数据源连接失败"]
    report = {"meta": {"code": "600519", "name": "贵州茅台", "usage": {},
                       "source": "desktop"},
              "chapters": results, "snapshot": snapshot, "full_markdown": ""}
    monkeypatch.setattr(report_generator, "chat", lambda *args, **kwargs: ("> 新点评", {"total_tokens": 8}))
    updated = report_generator.retry_report_chapter(report, "ch1_quote")
    assert updated["chapters"][0]["state"] == "ok"
    assert updated["chapters"][0]["data_warnings"] == ["数据源连接失败"]
    assert updated["meta"]["source"] == "desktop"
    assert "新点评" in updated["full_markdown"]
