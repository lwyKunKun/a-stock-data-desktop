import time

import pytest
from fastapi import HTTPException

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
    report_task._save_report("600519", {"full_markdown": "cached", "meta": {}})
    result = report_task.create_task("600519")
    assert result["status"] == "done"
    assert result["cached"] is True


def test_background_task_reaches_done(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)

    def fake_generate(code, on_progress=None):
        if on_progress:
            on_progress({"status": "generating", "progress": {"done": 6, "total": 12}})
        return {"code": code, "name": "贵州茅台", "meta": {"code": code, "name": "贵州茅台"},
                "chapters": [], "full_markdown": "# 报告"}

    monkeypatch.setattr(report_generator, "generate_report", fake_generate)
    created = report_task.create_task("600519", refresh=True)
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
    assert item["total_tokens"] == 12345
    assert result["industries"] == ["白酒"]
    filtered = report_index.list_reports(industry="其他")
    assert filtered["items"] == []


def test_invalid_code_returns_400():
    with pytest.raises(HTTPException) as exc:
        report_routes._stock_code("not-a-code")
    assert exc.value.status_code == 400


def test_missing_report_returns_null(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    assert report_routes.report("688825", date=None) is None
