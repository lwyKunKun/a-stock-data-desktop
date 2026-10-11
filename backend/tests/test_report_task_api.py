import time

import pytest
from fastapi import HTTPException

from app.api import report_routes
from app.services import report_generator, report_publisher, report_task


def _use_tmp_dirs(monkeypatch, tmp_path):
    task_dir = tmp_path / "tasks"
    report_dir = tmp_path / "reports"
    task_dir.mkdir()
    report_dir.mkdir()
    monkeypatch.setattr(report_task, "TASK_DIR", task_dir)
    monkeypatch.setattr(report_task, "REPORT_DIR", report_dir)


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
    monkeypatch.setattr(report_publisher, "publish_report", lambda report: {"ok": True})
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
    assert saved["meta"]["publication"]["ok"] is True
    assert saved["full_markdown"] == "# 报告"


def test_report_config_and_invalid_code():
    config = report_routes.report_config()
    assert len(config["chapters"]) == 12
    with pytest.raises(HTTPException) as exc:
        report_routes._stock_code("not-a-code")
    assert exc.value.status_code == 400
