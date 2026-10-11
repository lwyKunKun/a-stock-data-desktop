"""全维度报告后台任务与文件缓存。"""
import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.chapters import CHAPTERS, initial_chapter_states
from app.services import report_index

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
TASK_DIR = DATA_DIR / "tasks"
REPORT_DIR = DATA_DIR / "reports"
TASK_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

_ACTIVE_STATES = {"pending", "aggregating", "generating", "assembling", "retrying"}
_write_lock = threading.RLock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _task_path(code: str) -> Path:
    return TASK_DIR / f"{code}.json"


def _lock_path(code: str) -> Path:
    return TASK_DIR / f"{code}.lock"


def _validated_day(day: Optional[str]) -> str:
    value = day or _today()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date 须为 YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date 不是有效日期") from exc
    return value


def _report_path(code: str, day: Optional[str] = None) -> Path:
    return REPORT_DIR / f"{_validated_day(day)}_{code}.json"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def _atomic_write_json(path: Path, value: dict) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


def _write_status(code: str, patch: dict) -> dict:
    with _write_lock:
        status = _read_json(_task_path(code)) or {"code": code}
        status.update(patch)
        status["updated_at"] = _now()
        _atomic_write_json(_task_path(code), status)
        return status


def _save_report(code: str, report: dict) -> None:
    with _write_lock:
        json_path = _report_path(code)
        _atomic_write_json(json_path, report)
        markdown = report.get("full_markdown") or ""
        _atomic_write_text(json_path.with_suffix(".md"), markdown)
        # 同步 SQLite 索引，支撑报告列表页按日期/行业筛选
        report_index.upsert_report(report, day=_today(), db_path=None)


def load_report(code: str, day: Optional[str] = None) -> Optional[dict]:
    return _read_json(_report_path(code, day))


def get_task_status(code: str) -> Optional[dict]:
    return _read_json(_task_path(code))


def _is_fresh(status: dict) -> bool:
    raw = status.get("updated_at")
    if not raw:
        return False
    try:
        updated = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (datetime.now() - updated).total_seconds() < settings.REPORT_TASK_STALE_SECONDS


def _acquire_creation_lock(code: str) -> bool:
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
                return _acquire_creation_lock(code)
        except FileNotFoundError:
            return _acquire_creation_lock(code)
        return False


def _release_creation_lock(code: str) -> None:
    try:
        _lock_path(code).unlink()
    except FileNotFoundError:
        pass


def _initial_status(code: str, task_id: str, operation: str = "generate") -> dict:
    return {
        "task_id": task_id,
        "code": code,
        "operation": operation,
        "status": "pending",
        "cached": False,
        "current_chapter": None,
        "chapters": initial_chapter_states(),
        "progress": {"done": 0, "total": len(CHAPTERS)},
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
        "pid": os.getpid(),
    }


def _progress_callback(code: str):
    def update(patch: dict) -> None:
        allowed = {"status", "current_chapter", "chapters", "progress", "error"}
        _write_status(code, {key: value for key, value in patch.items() if key in allowed})

    return update


def _run_generate(code: str) -> None:
    try:
        _write_status(code, {"status": "aggregating"})
        from app.services.report_generator import generate_report

        report = generate_report(code, on_progress=_progress_callback(code))
        _write_status(code, {"status": "assembling"})
        _save_report(code, report)

        _write_status(code, {
            "status": "done",
            "progress": {"done": len(CHAPTERS), "total": len(CHAPTERS)},
            "current_chapter": None,
        })
    except Exception as exc:
        _write_status(code, {"status": "failed", "error": str(exc), "current_chapter": None})


def create_task(code: str, refresh: bool = False) -> dict:
    if not refresh:
        report = load_report(code)
        if report is not None:
            return {
                "code": code,
                "status": "done",
                "cached": True,
                "progress": {"done": len(CHAPTERS), "total": len(CHAPTERS)},
            }

    existing = get_task_status(code)
    if existing and existing.get("status") in _ACTIVE_STATES and _is_fresh(existing):
        return {**existing, "already_running": True}

    if not _acquire_creation_lock(code):
        existing = get_task_status(code)
        if existing:
            return {**existing, "already_running": True}
        return {"code": code, "status": "pending", "already_running": True}

    try:
        task_id = uuid.uuid4().hex
        status = _initial_status(code, task_id)
        _atomic_write_json(_task_path(code), status)
        threading.Thread(target=_run_generate, args=(code,), daemon=True, name=f"report-{code}").start()
        return status
    finally:
        _release_creation_lock(code)


def _run_retry_chapter(code: str, key: str) -> None:
    try:
        report = load_report(code)
        if report is None:
            raise FileNotFoundError(f"未找到 {code} 的当日报告")
        from app.services.report_generator import retry_report_chapter

        updated = retry_report_chapter(report, key, on_progress=_progress_callback(code))
        _save_report(code, updated)
        _write_status(code, {
            "status": "done",
            "progress": {"done": len(CHAPTERS), "total": len(CHAPTERS)},
            "current_chapter": None,
        })
    except Exception as exc:
        _write_status(code, {"status": "failed", "error": str(exc), "current_chapter": None})


def retry_chapter(code: str, key: str) -> dict:
    if key not in {chapter["key"] for chapter in CHAPTERS}:
        raise ValueError(f"未知章节: {key}")
    if load_report(code) is None:
        raise FileNotFoundError(f"未找到 {code} 的当日报告")
    existing = get_task_status(code)
    if existing and existing.get("status") in _ACTIVE_STATES and _is_fresh(existing):
        return {**existing, "already_running": True}
    status = _initial_status(code, uuid.uuid4().hex, operation="retry_chapter")
    status.update({"status": "retrying", "current_chapter": key})
    _atomic_write_json(_task_path(code), status)
    threading.Thread(
        target=_run_retry_chapter,
        args=(code, key),
        daemon=True,
        name=f"report-{code}-{key}",
    ).start()
    return status
