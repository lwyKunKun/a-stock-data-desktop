"""纯数据采集任务的 mock 测试 —— 不触真实外部数据源。"""
import time

import pytest
from fastapi import HTTPException

from app.api import data_routes
from app.services import data_task, full_aggregator


def _use_tmp_dirs(monkeypatch, tmp_path):
    task_dir = tmp_path / "tasks"
    snapshot_dir = tmp_path / "snapshots"
    task_dir.mkdir()
    snapshot_dir.mkdir()
    monkeypatch.setattr(data_task, "TASK_DIR", task_dir)
    monkeypatch.setattr(data_task, "SNAPSHOT_DIR", snapshot_dir)


def _fake_snapshot(code: str) -> dict:
    return {
        "code": code, "name": "贵州茅台", "fetched_at": "2026-10-11 10:00:00",
        "chapters": {}, "errors": {}, "source_errors": {},
    }


def test_cached_snapshot_skips_task(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    data_task._save_snapshot("600519", {"snapshot": True})
    result = data_task.create_collect_task("600519")
    assert result["status"] == "done"
    assert result["cached"] is True


def test_reuse_report_snapshot(monkeypatch, tmp_path):
    """当日已有 AI 报告时，直接复用其中的完整数据，不重新抓取。"""
    _use_tmp_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        data_task, "_try_reuse_report",
        lambda code: {"code": code, "chapters": [], "cached": True},
    )
    called = {"n": 0}

    def fake_build(code, on_progress=None):
        called["n"] += 1
        return _fake_snapshot(code)

    monkeypatch.setattr(full_aggregator, "build_full_snapshot", fake_build)
    result = data_task.create_collect_task("600519")
    assert result["status"] == "done"
    assert called["n"] == 0


def test_background_collect_reaches_done(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)

    def fake_build(code, on_progress=None):
        if on_progress:
            on_progress({"status": "aggregating", "current_chapter": "数据源：quote"})
        return _fake_snapshot(code)

    monkeypatch.setattr(full_aggregator, "build_full_snapshot", fake_build)
    created = data_task.create_collect_task("600519", refresh=True)
    assert created["status"] == "pending"

    deadline = time.time() + 3
    status = None
    while time.time() < deadline:
        status = data_task.get_data_status("600519")
        if status and status["status"] == "done":
            break
        time.sleep(0.02)
    assert status["status"] == "done"

    saved = data_task.load_data("600519")
    assert saved["code"] == "600519"
    assert saved["name"] == "贵州茅台"
    # 十二章 data_md 全部渲染出来
    assert len(saved["chapters"]) == 12
    assert all(chapter["data_md"] for chapter in saved["chapters"])
    assert "snapshot" in saved


def test_full_data_endpoint_404_and_invalid_date(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as exc:
        data_routes.full_data("600519", date=None)
    assert exc.value.status_code == 404

    data_task._save_snapshot("600519", {"code": "600519"})
    with pytest.raises(HTTPException) as exc:
        data_routes.full_data("600519", date="../../etc")
    assert exc.value.status_code == 400
    result = data_routes.full_data("600519", date=None)
    assert result["code"] == "600519"


def test_collect_endpoint_status_code(monkeypatch, tmp_path):
    _use_tmp_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(full_aggregator, "build_full_snapshot",
                        lambda code, on_progress=None: _fake_snapshot(code))
    response = type("Response", (), {"status_code": None})()
    result = data_routes.collect("600519", data_routes.CollectRequest(refresh=False), response)
    assert response.status_code == 202
    assert result["status"] in {"pending", "already_running"}
