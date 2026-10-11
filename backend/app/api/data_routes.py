"""全维度纯数据查询 API —— 零 token，查询即展示接口全部数据。

端点：
  POST /api/data/{code}/collect   发起数据采集（后台任务，按日缓存）
  GET  /api/data/{code}/status    查询采集进度（前端轮询）
  GET  /api/data/{code}           获取完整十二章数据（含各章 Markdown 表格）
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.core.ticker import norm_ticker
from app.services.data_task import (
    create_collect_task,
    get_data_status,
    load_data,
)

router = APIRouter(prefix="/api/data", tags=["full-data"])


class CollectRequest(BaseModel):
    refresh: bool = False


def _stock_code(code: str) -> str:
    try:
        return norm_ticker(code, stock_only=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{code}/collect")
def collect(code: str, payload: CollectRequest, response: Response):
    """发起采集：已有当日缓存直接返回 done；否则启动后台采集任务。"""
    result = create_collect_task(_stock_code(code), refresh=payload.refresh)
    if result.get("cached") or result.get("already_running"):
        response.status_code = 200
    else:
        response.status_code = 202
    return result


@router.get("/{code}/status")
def status(code: str):
    c = _stock_code(code)
    result = get_data_status(c)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 {c} 的数据采集任务")
    return result


@router.get("/{code}")
def full_data(code: str, date: Optional[str] = Query(None, description="历史日期 YYYY-MM-DD")):
    """完整数据：十二章 Markdown + 原始快照 + 数据源错误明细。"""
    c = _stock_code(code)
    try:
        result = load_data(c, day=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 {c} 的数据，请先调用 collect 采集")
    return result
