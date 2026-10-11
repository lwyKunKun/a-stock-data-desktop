"""已生成报告的 SQLite 轻量索引。

报告正文仍按天存 JSON 文件（见 report_task.REPORT_DIR），本模块只维护一张索引表，
支撑列表页按日期/行业筛选；首次列表查询时把历史报告文件一次性回填进索引。

选 SQLite 而非引入独立数据库：Python 内置 sqlite3 零安装，索引只存 meta 级别的
少量字段，正文读取仍走原 JSON 文件，不重复存一份大数据。
"""
import json
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "reports_index.db"

_lock = threading.RLock()

_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.json$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
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
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    db = db_path or DB_PATH
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _row_from_report(report: dict, day: Optional[str] = None) -> Optional[tuple]:
    meta = report.get("meta") or {}
    code = str(meta.get("code") or report.get("code") or "")
    if not code:
        return None
    generated_at = str(meta.get("generated_at") or "")
    date = day or generated_at[:10] or datetime.now().strftime("%Y-%m-%d")
    usage = meta.get("usage") or {}

    def _num(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return (
        code,
        str(meta.get("name") or ""),
        date,
        str(meta.get("industry") or ""),
        generated_at,
        str(meta.get("model") or ""),
        int(_num(usage.get("total_tokens"))),
        _num(meta.get("duration_s")),
        meta.get("price"),
        meta.get("change_pct"),
        meta.get("pe_ttm"),
    )


_UPSERT_SQL = """
INSERT INTO reports (code, name, date, industry, generated_at, model, total_tokens,
                     duration_s, price, change_pct, pe_ttm)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(code, date) DO UPDATE SET
    name=excluded.name,
    industry=excluded.industry,
    generated_at=excluded.generated_at,
    model=excluded.model,
    total_tokens=excluded.total_tokens,
    duration_s=excluded.duration_s,
    price=excluded.price,
    change_pct=excluded.change_pct,
    pe_ttm=excluded.pe_ttm
"""


def upsert_report(report: dict, day: Optional[str] = None,
                  db_path: Optional[Path] = None) -> None:
    """报告落盘时同步索引；同一股票同一天重复生成会覆盖旧行。"""
    row = _row_from_report(report, day)
    if row is None:
        return
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute(_UPSERT_SQL, row)
            conn.commit()
        finally:
            conn.close()


def backfill(report_dir: Path, db_path: Optional[Path] = None) -> None:
    """把 reports/ 目录下尚未入库的历史报告文件一次性回填（幂等，只跑一遍）。"""
    with _lock:
        conn = _connect(db_path)
        try:
            done = conn.execute(
                "SELECT value FROM meta WHERE key = 'backfilled'"
            ).fetchone()
            if done:
                return
            for path in sorted(Path(report_dir).glob("*.json")):
                match = _FILE_RE.match(path.name)
                if not match:
                    continue
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                row = _row_from_report(report, day=match.group(1))
                if row:
                    conn.execute(_UPSERT_SQL, row)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('backfilled', ?)",
                (datetime.now().isoformat(timespec="seconds"),),
            )
            conn.commit()
        finally:
            conn.close()


def list_reports(date: Optional[str] = None, industry: Optional[str] = None,
                 db_path: Optional[Path] = None) -> dict:
    """按日期/行业筛选报告列表，并返回可供筛选的日期与行业选项。"""
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT code, name, date, industry, generated_at, model,
                       total_tokens, duration_s, price, change_pct, pe_ttm
                FROM reports
                WHERE (? IS NULL OR date = ?) AND (? IS NULL OR industry = ?)
                ORDER BY date DESC, generated_at DESC, code
                """,
                (date, date, industry, industry),
            ).fetchall()
            dates = [row["date"] for row in conn.execute(
                "SELECT DISTINCT date FROM reports ORDER BY date DESC"
            ).fetchall()]
            industries = [row["industry"] for row in conn.execute(
                "SELECT DISTINCT industry FROM reports "
                "WHERE industry != '' ORDER BY industry"
            ).fetchall()]
        finally:
            conn.close()
    items = [{key: row[key] for key in row.keys()} for row in rows]
    return {"items": items, "dates": dates, "industries": industries}
