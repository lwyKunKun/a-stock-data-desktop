import json
import sqlite3
import time

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import report_routes
from app.services import report_generator, report_index, report_task


def _use_tmp_dirs(monkeypatch, tmp_path):
    task_dir = tmp_path / "tasks"
    report_dir = tmp_path / "reports"
    task_dir.mkdir()
    report_dir.mkdir()
    monkeypatch.setattr(report_task, "TASK_DIR", task_dir)
    monkeypatch.setattr(report_task, "REPORT_DIR", report_dir)
    monkeypatch.setattr(report_index, "DB_PATH", tmp_path / "index.db")


def test_cached_report_skips_task(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    report_task._save_report("600519", {
        "full_markdown": "cached",
        "meta": {"code": "600519", "source": "desktop"},
    })
    result = report_task.create_task("600519", source="web")
    assert result["status"] == "done"
    assert result["cached"] is True
    assert report_task.load_report("600519")["meta"]["source"] == "desktop"
    assert report_index.list_reports()["items"][0]["source"] == "desktop"


@pytest.mark.parametrize("source", ["desktop", "web"])
def test_background_task_reaches_done_with_source(monkeypatch, tmp_path, source):
    _use_tmp_dirs(monkeypatch, tmp_path)

    def fake_generate(code, on_progress=None):
        if on_progress:
            on_progress({"status": "generating", "progress": {"done": 6, "total": 12}})
        return {"code": code, "name": "贵州茅台", "meta": {"code": code, "name": "贵州茅台"},
                "chapters": [], "full_markdown": "# 报告"}

    monkeypatch.setattr(report_generator, "generate_report", fake_generate)
    created = report_task.create_task("600519", refresh=True, source=source)
    assert created["status"] == "pending"
    deadline = time.time() + 3
    status = None
    while time.time() < deadline:
        status = report_task.get_task_status("600519")
        if status and status["status"] == "done":
            break
        time.sleep(0.02)
    assert status["status"] == "done"
    saved = report_task.load_report("600519")
    assert saved["full_markdown"] == "# 报告"
    assert saved["meta"]["source"] == source
    assert report_index.list_reports()["items"][0]["source"] == source


def test_report_list_indexed(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    report_task._save_report("600519", {
        "full_markdown": "# 报告",
        "meta": {"code": "600519", "name": "贵州茅台", "industry": "白酒",
                 "generated_at": "2026-10-11 10:00:00", "model": "kimi-k2-0711-preview",
                 "usage": {"total_tokens": 12345}},
    })
    report_index.backfill(report_task.REPORT_DIR)
    result = report_index.list_reports()
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["code"] == "600519"
    assert item["industry"] == "白酒"
    assert item["source"] is None
    assert item["total_tokens"] == 12345
    assert result["industries"] == ["白酒"]
    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 10
    assert result["total_pages"] == 1
    filtered = report_index.list_reports(industry="其他")
    assert filtered["items"] == []
    assert filtered["total"] == 0
    assert filtered["total_pages"] == 0


def test_refresh_updates_report_source(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    report_task._save_report("600519", {
        "full_markdown": "旧报告",
        "meta": {"code": "600519", "source": "desktop"},
    })

    def fake_generate(code, on_progress=None):
        return {
            "code": code,
            "meta": {"code": code},
            "chapters": [],
            "full_markdown": "新报告",
        }

    monkeypatch.setattr(report_generator, "generate_report", fake_generate)
    report_task.create_task("600519", refresh=True, source="web")
    deadline = time.time() + 3
    while time.time() < deadline:
        status = report_task.get_task_status("600519")
        if status and status["status"] == "done":
            break
        time.sleep(0.02)

    saved = report_task.load_report("600519")
    assert saved["full_markdown"] == "新报告"
    assert saved["meta"]["source"] == "web"
    assert report_index.list_reports()["items"][0]["source"] == "web"


def test_report_index_migrates_legacy_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE reports (
            code TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            date TEXT NOT NULL,
            industry TEXT NOT NULL DEFAULT '',
            generated_at TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            total_tokens INTEGER NOT NULL DEFAULT 0,
            duration_s REAL NOT NULL DEFAULT 0,
            price REAL,
            change_pct REAL,
            pe_ttm REAL,
            PRIMARY KEY (code, date)
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO reports (code, name, date) VALUES ('600519', '贵州茅台', '2026-10-11');
    """)
    conn.close()

    first = report_index.list_reports(db_path=db_path)
    second = report_index.list_reports(db_path=db_path)
    assert first["items"][0]["source"] is None
    assert second["items"][0]["source"] is None

    conn = sqlite3.connect(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(reports)")]
    conn.close()
    assert columns.count("source") == 1


def test_generate_request_rejects_unknown_source():
    with pytest.raises(ValidationError):
        report_routes.GenerateRequest(refresh=False, source="mobile")


def test_report_list_pagination_and_filters(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    for index in range(12):
        day = "2026-10-11" if index < 8 else "2026-10-10"
        industry = "白酒" if index % 2 == 0 else "食品"
        report_index.upsert_report({
            "meta": {
                "code": f"60{index:04d}",
                "name": f"股票{index}",
                "industry": industry,
                "generated_at": f"{day} 10:{index:02d}:00",
            }
        }, day=day)

    first = report_index.list_reports()
    assert len(first["items"]) == 10
    assert first["total"] == 12
    assert first["total_pages"] == 2
    assert first["page"] == 1

    second = report_index.list_reports(page=2)
    assert len(second["items"]) == 2
    assert second["page"] == 2
    assert {item["code"] for item in first["items"]}.isdisjoint(
        item["code"] for item in second["items"]
    )

    filtered = report_index.list_reports(
        date="2026-10-11", industry="白酒", page_size=3
    )
    assert filtered["total"] == 4
    assert filtered["total_pages"] == 2
    assert len(filtered["items"]) == 3

    last = report_index.list_reports(page=99)
    assert last["page"] == 2
    assert len(last["items"]) == 2


def test_invalid_code_returns_400():
    with pytest.raises(HTTPException) as exc:
        report_routes._stock_code("not-a-code")
    assert exc.value.status_code == 400


def test_missing_report_returns_null(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    assert report_routes.report("688825", date=None) is None


def _write_historical_report(day, code, payload):
    path = report_task.REPORT_DIR / f"{day}_{code}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_report_reads_requested_historical_date(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    expected = {
        "code": "300821",
        "name": "东岳硅材",
        "chapters": [{"key": "ch1_quote", "title": "一、实时行情", "state": "ok"}],
        "full_markdown": "# 2026-10-11 报告",
        "meta": {"generated_at": "2026-10-11 19:54:38"},
    }
    _write_historical_report("2026-10-11", "300821", expected)

    assert report_routes.report("300821", date="2026-10-11") == expected


def test_same_stock_reports_are_isolated_by_date(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    older = {"code": "300821", "full_markdown": "旧报告"}
    newer = {"code": "300821", "full_markdown": "新报告"}
    _write_historical_report("2026-10-10", "300821", older)
    _write_historical_report("2026-10-11", "300821", newer)

    assert report_routes.report("300821", date="2026-10-10") == older
    assert report_routes.report("300821", date="2026-10-11") == newer


def test_missing_historical_report_returns_null(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    assert report_routes.report("300821", date="2026-10-11") is None


@pytest.mark.parametrize("value", ["2026/10/11", "2026-02-30"])
def test_invalid_report_date_returns_400(monkeypatch, tmp_path, value):
    _use_tmp_dirs(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        report_routes.report("300821", date=value)
    assert exc.value.status_code == 400


def test_report_without_date_reads_today(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(report_task, "_today", lambda: "2026-10-12")
    expected = {"code": "300821", "full_markdown": "今日报告"}
    _write_historical_report("2026-10-12", "300821", expected)

    assert report_routes.report("300821", date=None) == expected
