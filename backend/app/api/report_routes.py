"""全维度报告异步任务 API。"""
from datetime import date as date_type
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.ticker import norm_ticker
from app.services import report_index
from app.services.report_task import (
    REPORT_DIR,
    create_task,
    get_task_status,
    load_report,
    retry_chapter,
)

router = APIRouter(prefix="/api/report", tags=["full-report"])


class GenerateRequest(BaseModel):
    refresh: bool = False
    source: Literal["desktop", "web"] = "web"


def _stock_code(code: str) -> str:
    try:
        return norm_ticker(code, stock_only=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/list")
def report_list(
    report_date: Optional[date_type] = Query(None, alias="date"),
    industry: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """已生成报告列表（SQLite 索引），支持按日期/行业筛选和分页。"""
    report_index.backfill(REPORT_DIR)
    normalized_industry = industry.strip() if industry else None
    return report_index.list_reports(
        date=report_date.isoformat() if report_date else None,
        industry=normalized_industry or None,
        page=page,
        page_size=page_size,
    )


@router.post("/{code}/generate")
def generate(code: str, payload: GenerateRequest, response: Response):
    result = create_task(
        _stock_code(code), refresh=payload.refresh, source=payload.source
    )
    if result.get("cached") or result.get("already_running"):
        response.status_code = 200
    else:
        response.status_code = 202
    return result


@router.get("/{code}/status")
def status(code: str):
    c = _stock_code(code)
    result = get_task_status(c)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 {c} 的报告任务")
    return result


@router.post("/{code}/chapter/{key}/retry", status_code=202)
def retry_report_chapter(code: str, key: str):
    c = _stock_code(code)
    try:
        return retry_chapter(c, key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{code}/markdown", response_class=PlainTextResponse)
def report_markdown(code: str, date: Optional[str] = Query(None)):
    c = _stock_code(code)
    try:
        report = load_report(c, day=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail=f"未找到 {c} 的报告")
    return PlainTextResponse(report.get("full_markdown") or "", media_type="text/markdown; charset=utf-8")


@router.get("/{code}")
def report(code: str, date: Optional[str] = Query(None)):
    """读取报告；尚未生成时返回 null，供前端正常进入首次生成状态。"""
    c = _stock_code(code)
    try:
        return load_report(c, day=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
