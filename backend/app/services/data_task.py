"""全维度纯数据采集任务 —— 零 token，只聚合数据不调 AI。

与报告任务（report_task.py）的区别：不生成 AI 点评、不发布，只把
build_full_snapshot 的完整十二章数据按日缓存，供前端「查询即展示全部数据」。

缓存策略：
  - 优先复用当日 AI 报告缓存（load_report），里面已含完整 snapshot 与各章 data_md，零成本
  - 否则后台线程重新跑 build_full_snapshot，结果落盘 data/snapshots/{date}_{code}.json
"""
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.paths import get_data_dir
from app.services.chapters import CHAPTERS
from app.services.chapter_md import render_chapter_data

DATA_DIR = get_data_dir()
SNAPSHOT_DIR = DATA_DIR / "snapshots"
TASK_DIR = DATA_DIR / "tasks"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
TASK_DIR.mkdir(parents=True, exist_ok=True)

_ACTIVE_STATES = {"pending", "aggregating"}
_write_lock = threading.RLock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _task_path(code: str) -> Path:
    return TASK_DIR / f"data_{code}.json"


def _lock_path(code: str) -> Path:
    return TASK_DIR / f"data_{code}.lock"


def _snapshot_path(code: str, day: Optional[str] = None) -> Path:
    return SNAPSHOT_DIR / f"{day or _today()}_{code}.json"


# 复用报告任务的文件读写工具，避免重复实现原子写/读逻辑
from app.services.report_task import (  # noqa: E402
    _atomic_write_json,
    _read_json,
    _validated_day,
    _is_fresh,
)


def _write_status(code: str, patch: dict) -> dict:
    with _write_lock:
        status = _read_json(_task_path(code)) or {"code": code}
        status.update(patch)
        status["updated_at"] = _now()
        _atomic_write_json(_task_path(code), status)
        return status


def _chapter_md_list(snapshot: dict) -> list[dict]:
    """把完整快照渲染成各章 Markdown 表格（与 AI 报告的 data_md 同源）。"""
    return [
        {
            "key": item["key"],
            "title": item["title"],
            "data_md": render_chapter_data(item["key"], snapshot),
        }
        for item in CHAPTERS
    ]


def _data_payload(snapshot: dict, cached: bool) -> dict:
    """统一的数据响应结构：各章 data_md + 错误信息 + 完整原始快照。"""
    return {
        "code": snapshot.get("code"),
        "name": snapshot.get("name"),
        "fetched_at": snapshot.get("fetched_at") or _now(),
        "cached": cached,
        "chapters": _chapter_md_list(snapshot),
        "errors": snapshot.get("errors") or {},
        "source_errors": snapshot.get("source_errors") or {},
        "snapshot": snapshot,
    }


def _save_snapshot(code: str, payload: dict) -> None:
    with _write_lock:
        _atomic_write_json(_snapshot_path(code), payload)


def load_data(code: str, day: Optional[str] = None) -> Optional[dict]:
    """读取按日缓存的纯数据快照；day 参数会校验防路径穿越。"""
    return _read_json(_snapshot_path(code, _validated_day(day)))


def get_data_status(code: str) -> Optional[dict]:
    return _read_json(_task_path(code))


def _try_reuse_report(code: str) -> Optional[dict]:
    """当日已有 AI 报告时直接复用其中的完整数据，零成本零等待。"""
    from app.services.report_task import load_report

    report = load_report(code)
    if not report or not report.get("snapshot"):
        return None
    snapshot = report["snapshot"]
    # 报告的 snapshot 没有 fetched_at，用报告生成时间代替
    snapshot.setdefault("fetched_at", (report.get("meta") or {}).get("generated_at") or _now())
    return _data_payload(snapshot, cached=True)


def _run_collect(code: str) -> None:
    try:
        _write_status(code, {"status": "aggregating", "current_chapter": "正在连接数据源…"})

        def on_progress(patch: dict) -> None:
            allowed = {"current_chapter", "progress"}
            _write_status(code, {key: value for key, value in patch.items() if key in allowed})

        from app.services.full_aggregator import build_full_snapshot

        snapshot = build_full_snapshot(code, on_progress=on_progress)
        payload = _data_payload(snapshot, cached=False)
        _save_snapshot(code, payload)
        _write_status(code, {
            "status": "done",
            "current_chapter": None,
            "error": None,
            "fetched_at": payload["fetched_at"],
        })
    except Exception as exc:
        _write_status(code, {"status": "failed", "error": str(exc), "current_chapter": None})


def _acquire_lock(code: str) -> bool:
    path = _lock_path(code)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = datetime.now().timestamp() - path.stat().st_mtime
            if age >= settings.REPORT_TASK_STALE_SECONDS:
                path.unlink()
                return _acquire_lock(code)
        except FileNotFoundError:
            return _acquire_lock(code)
        return False


def _release_lock(code: str) -> None:
    try:
        _lock_path(code).unlink()
    except FileNotFoundError:
        pass


def create_collect_task(code: str, refresh: bool = False) -> dict:
    """发起数据采集：先查缓存（含 AI 报告复用），再决定是否后台采集。"""
    if not refresh:
        cached = load_data(code)
        if cached is not None:
            return {"code": code, "status": "done", "cached": True}
        reused = _try_reuse_report(code)
        if reused is not None:
            # 落一份纯数据缓存，后续 load_data 直接命中
            _save_snapshot(code, reused)
            return {"code": code, "status": "done", "cached": True, "reused_report": True}

    existing = get_data_status(code)
    if existing and existing.get("status") in _ACTIVE_STATES and _is_fresh(existing):
        return {**existing, "already_running": True}

    if not _acquire_lock(code):
        existing = get_data_status(code)
        if existing:
            return {**existing, "already_running": True}
        return {"code": code, "status": "pending", "already_running": True}

    try:
        status = {
            "task_id": uuid.uuid4().hex,
            "code": code,
            "status": "pending",
            "cached": False,
            "current_chapter": None,
            "progress": {"done": 0, "total": len(CHAPTERS)},
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
            "pid": os.getpid(),
        }
        _atomic_write_json(_task_path(code), status)
        threading.Thread(target=_run_collect, args=(code,), daemon=True,
                         name=f"data-{code}").start()
        return status
    finally:
        _release_lock(code)
