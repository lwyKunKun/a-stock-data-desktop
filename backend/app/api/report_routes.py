"""全维度报告异步任务 API。"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.ticker import norm_ticker
from app.services.chapters import CHAPTERS
from app.services.report_task import (
    create_task,
    get_task_status,
    load_report,
    retry_chapter,
    retry_publish,
)

router = APIRouter(prefix="/api/report", tags=["full-report"])


class GenerateRequest(BaseModel):
    refresh: bool = False


def _stock_code(code: str) -> str:
    try:
        return norm_ticker(code, stock_only=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/config")
def report_config():
    return {
        "auto_trigger_default": settings.REPORT_AUTO_TRIGGER_DEFAULT,
        "obsidian_sync": settings.OBSIDIAN_SYNC_ENABLED,
        "stock_review_publish": settings.STOCK_REVIEW_PUBLISH_ENABLED,
        "chapters": CHAPTERS,
    }


@router.post("/{code}/generate")
def generate(code: str, payload: GenerateRequest, response: Response):
    result = create_task(_stock_code(code), refresh=payload.refresh)
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


@router.post("/{code}/publish/retry", status_code=202)
def retry_report_publish(code: str):
    c = _stock_code(code)
    try:
        return retry_publish(c)
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
    c = _stock_code(code)
    try:
        result = load_report(c, day=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 {c} 的报告")
    return result
