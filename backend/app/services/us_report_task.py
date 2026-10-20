import os
import threading
import uuid
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.core.instrument import Instrument
from app.core.paths import get_data_dir
from app.services import report_index
from app.services.report_task import _atomic_write_json, _atomic_write_text, _is_fresh, _read_json, _validated_day
from app.services.us_chapters import US_CHAPTERS, US_CHAPTER_KEYS, initial_us_chapter_states
from app.services.us_report_generator import generate_us_report, retry_us_report_chapter

DATA_DIR = get_data_dir(); TASK_DIR = DATA_DIR / "tasks"; REPORT_DIR = DATA_DIR / "reports"
TASK_DIR.mkdir(parents=True, exist_ok=True); REPORT_DIR.mkdir(parents=True, exist_ok=True)
_lock = threading.RLock()


def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _today(): return datetime.now().strftime("%Y-%m-%d")
def _task_path(i): return TASK_DIR / f"report_{i.canonical_key}.json"
def _lock_path(i): return TASK_DIR / f"report_{i.canonical_key}.lock"
def _report_path(i, day=None): return REPORT_DIR / f"{_validated_day(day)}_{i.canonical_key}.json"


def _write_status(i, patch):
    with _lock:
        status = _read_json(_task_path(i)) or {"market": "US", "code": i.symbol}
        status.update(patch); status["updated_at"] = _now(); _atomic_write_json(_task_path(i), status); return status


def _callback(i):
    return lambda patch: _write_status(i, {k: v for k, v in patch.items() if k in {"status", "current_chapter", "chapters", "progress", "error"}})


def load_us_report(i: Instrument, day: Optional[str] = None): return _read_json(_report_path(i, day))
def get_us_report_status(i: Instrument): return _read_json(_task_path(i))


def _save(i, report):
    path = _report_path(i); _atomic_write_json(path, report); _atomic_write_text(path.with_suffix(".md"), report.get("full_markdown") or "")
    report_index.upsert_report(report, day=_today())


def _run_generate(i, source):
    try:
        _write_status(i, {"status": "aggregating"}); report = generate_us_report(i, _callback(i)); report.setdefault("meta", {})["source"] = source
        _write_status(i, {"status": "assembling"}); _save(i, report)
        _write_status(i, {"status": "done", "progress": {"done": len(US_CHAPTERS), "total": len(US_CHAPTERS)}, "current_chapter": None})
    except Exception as exc: _write_status(i, {"status": "failed", "error": str(exc), "current_chapter": None})


def create_us_report_task(i: Instrument, refresh=False, source="web"):
    if not refresh and load_us_report(i) is not None:
        return {"market": "US", "code": i.symbol, "status": "done", "cached": True, "progress": {"done": len(US_CHAPTERS), "total": len(US_CHAPTERS)}}
    existing = get_us_report_status(i)
    if existing and existing.get("status") in {"pending", "aggregating", "generating", "assembling", "retrying"} and _is_fresh(existing): return {**existing, "already_running": True}
    lock = _lock_path(i)
    try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
    except FileExistsError: return existing or {"market": "US", "code": i.symbol, "status": "pending", "already_running": True}
    try:
        status = {"task_id": uuid.uuid4().hex, "market": "US", "code": i.symbol, "operation": "generate", "status": "pending", "cached": False,
                  "chapters": initial_us_chapter_states(), "progress": {"done": 0, "total": len(US_CHAPTERS)}, "current_chapter": None, "error": None,
                  "created_at": _now(), "updated_at": _now(), "pid": os.getpid()}
        _atomic_write_json(_task_path(i), status); threading.Thread(target=_run_generate, args=(i, source), daemon=True).start(); return status
    finally: lock.unlink(missing_ok=True)


def retry_us_chapter(i: Instrument, key: str):
    if key not in US_CHAPTER_KEYS: raise ValueError(f"未知章节: {key}")
    report = load_us_report(i)
    if report is None: raise FileNotFoundError(f"未找到 {i.symbol} 的当日报告")
    status = {"task_id": uuid.uuid4().hex, "market": "US", "code": i.symbol, "operation": "retry_chapter", "status": "retrying", "chapters": initial_us_chapter_states(), "progress": {"done": 0, "total": len(US_CHAPTERS)}, "current_chapter": key, "updated_at": _now()}
    _atomic_write_json(_task_path(i), status)
    def run():
        try: _save(i, retry_us_report_chapter(report, key, _callback(i))); _write_status(i, {"status": "done", "current_chapter": None, "progress": {"done": 10, "total": 10}})
        except Exception as exc: _write_status(i, {"status": "failed", "error": str(exc), "current_chapter": None})
    threading.Thread(target=run, daemon=True).start(); return status
