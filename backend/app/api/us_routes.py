from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.core.instrument import parse_us_instrument
from app.datasources.us.search import search_us_stocks
from app.services.us_data_task import create_us_collect_task, get_us_data_status, load_us_data

router = APIRouter(prefix="/api/us", tags=["us-market"])


class CollectRequest(BaseModel):
    refresh: bool = False


def _instrument(symbol: str):
    try:
        return parse_us_instrument(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=80), limit: int = Query(10, ge=1, le=20)):
    try:
        return search_us_stocks(q.strip(), limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"美股搜索失败: {exc}") from exc


@router.post("/data/{symbol}/collect")
def collect(symbol: str, payload: CollectRequest, response: Response):
    result = create_us_collect_task(_instrument(symbol), payload.refresh)
    response.status_code = 200 if result.get("cached") or result.get("already_running") else 202
    return result


@router.get("/data/{symbol}/status")
def status(symbol: str):
    result = get_us_data_status(_instrument(symbol))
    if result is None:
        raise HTTPException(404, "没有该股票的数据采集任务")
    return result


@router.get("/data/{symbol}")
def data(symbol: str, day: date_type | None = Query(None, alias="date")):
    try:
        result = load_us_data(_instrument(symbol), day.isoformat() if day else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "尚未采集该股票数据")
    return result
