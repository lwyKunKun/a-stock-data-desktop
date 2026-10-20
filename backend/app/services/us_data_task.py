import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.instrument import Instrument
from app.core.paths import get_data_dir
from app.services.report_task import _atomic_write_json, _is_fresh, _read_json, _validated_day
from app.services.us_aggregator import build_us_snapshot
from app.services.us_chapter_md import render_us_chapter_data
from app.services.us_chapters import US_CHAPTERS

DATA_DIR = get_data_dir()
SNAPSHOT_DIR, TASK_DIR = DATA_DIR / "snapshots", DATA_DIR / "tasks"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
TASK_DIR.mkdir(parents=True, exist_ok=True)
_lock = threading.RLock()


def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _today(): return datetime.now().strftime("%Y-%m-%d")
def _task_path(instrument): return TASK_DIR / f"data_{instrument.canonical_key}.json"
def _lock_path(instrument): return TASK_DIR / f"data_{instrument.canonical_key}.lock"
def _snapshot_path(instrument, day=None): return SNAPSHOT_DIR / f"{day or _today()}_{instrument.canonical_key}.json"


def _write_status(instrument: Instrument, patch: dict):
    with _lock:
        status = _read_json(_task_path(instrument)) or {"market": "US", "code": instrument.symbol}
        status.update(patch); status["updated_at"] = _now()
        _atomic_write_json(_task_path(instrument), status)
        return status


def _payload(snapshot: dict, cached: bool):
    return {"market": "US", "code": snapshot["code"], "name": snapshot["name"], "fetched_at": snapshot["fetched_at"],
            "cached": cached, "chapters": [{"key": item["key"], "title": item["title"],
            "data_md": render_us_chapter_data(item["key"], snapshot), "sources": snapshot.get("sources") or []} for item in US_CHAPTERS],
            "errors": snapshot.get("errors") or {}, "source_errors": snapshot.get("source_errors") or {}, "sources": snapshot.get("sources") or [], "snapshot": snapshot}


def load_us_data(instrument: Instrument, day: Optional[str] = None): return _read_json(_snapshot_path(instrument, _validated_day(day)))
def get_us_data_status(instrument: Instrument): return _read_json(_task_path(instrument))


def _run(instrument: Instrument):
    try:
        _write_status(instrument, {"status": "aggregating", "current_chapter": "正在连接美股数据源…"})
        snapshot = build_us_snapshot(instrument, lambda patch: _write_status(instrument, patch), settings.SEC_CONTACT)
        payload = _payload(snapshot, False)
        _atomic_write_json(_snapshot_path(instrument), payload)
        _write_status(instrument, {"status": "done", "current_chapter": None, "error": None, "fetched_at": payload["fetched_at"]})
    except Exception as exc:
        _write_status(instrument, {"status": "failed", "error": str(exc), "current_chapter": None})


def create_us_collect_task(instrument: Instrument, refresh: bool = False):
    if not refresh:
        cached = load_us_data(instrument)
        if cached is not None: return {"market": "US", "code": instrument.symbol, "status": "done", "cached": True}
    existing = get_us_data_status(instrument)
    if existing and existing.get("status") in {"pending", "aggregating"} and _is_fresh(existing):
        return {**existing, "already_running": True}
    lock_path = _lock_path(instrument)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
    except FileExistsError:
        return existing or {"market": "US", "code": instrument.symbol, "status": "pending", "already_running": True}
    try:
        status = {"task_id": uuid.uuid4().hex, "market": "US", "code": instrument.symbol, "status": "pending", "cached": False,
                  "current_chapter": None, "progress": {"done": 0, "total": len(US_CHAPTERS)}, "error": None,
                  "created_at": _now(), "updated_at": _now(), "pid": os.getpid()}
        _atomic_write_json(_task_path(instrument), status)
        threading.Thread(target=_run, args=(instrument,), daemon=True, name=f"us-data-{instrument.symbol}").start()
        return status
    finally:
        lock_path.unlink(missing_ok=True)
