from datetime import date as date_type
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.instrument import parse_us_instrument
from app.services.us_report_task import create_us_report_task, get_us_report_status, load_us_report, retry_us_chapter

router = APIRouter(prefix="/api/us/report", tags=["us-report"])


class GenerateRequest(BaseModel):
    refresh: bool = False
    source: Literal["desktop", "web"] = "web"


def _instrument(symbol: str):
    try:
        return parse_us_instrument(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{symbol}/generate")
def generate(symbol: str, payload: GenerateRequest, response: Response):
    result = create_us_report_task(_instrument(symbol), payload.refresh, payload.source)
    response.status_code = 200 if result.get("cached") or result.get("already_running") else 202
    return result


@router.get("/{symbol}/status")
def status(symbol: str):
    result = get_us_report_status(_instrument(symbol))
    if result is None:
        raise HTTPException(404, "没有该股票的报告任务")
    return result


@router.post("/{symbol}/chapter/{key}/retry", status_code=202)
def retry(symbol: str, key: str):
    try:
        return retry_us_chapter(_instrument(symbol), key)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400 if isinstance(exc, ValueError) else 404, str(exc)) from exc


@router.get("/{symbol}/markdown", response_class=PlainTextResponse)
def markdown(symbol: str, day: date_type | None = Query(None, alias="date")):
    report = load_us_report(_instrument(symbol), day.isoformat() if day else None)
    if report is None:
        raise HTTPException(404, "未找到报告")
    return report.get("full_markdown") or ""


@router.get("/{symbol}")
def report(symbol: str, day: date_type | None = Query(None, alias="date")):
    return load_us_report(_instrument(symbol), day.isoformat() if day else None)
