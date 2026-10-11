"""数据源仓库版本监控 API —— 提醒上游 a-stock-data 仓库有新提交时更新数据源。

端点：
  GET  /api/datasource/status  查询上游最新 commit 与本地确认状态（带 10 分钟服务端缓存）
  POST /api/datasource/ack     用户确认已知悉更新，不再提示当前版本
  POST /api/datasource/report  生成「已确认版本 → 最新版本」的更新报告（函数级差异 + 后端文件映射）
"""
from fastapi import APIRouter, HTTPException

from app.services import datasource_watch

router = APIRouter(prefix="/api/datasource", tags=["datasource"])


@router.get("/status")
def status():
    return datasource_watch.get_status()


@router.post("/ack")
def ack():
    return datasource_watch.acknowledge()


@router.post("/report")
def report():
    try:
        return datasource_watch.build_update_report()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
