"""数据源仓库版本监控 API —— 提醒上游 a-stock-data 仓库有新提交时更新数据源。

端点：
  GET  /api/datasource/status            查询上游最新 commit 与本地确认状态（带 10 分钟服务端缓存）
  POST /api/datasource/ack               用户确认已知悉更新，不再提示当前版本
  POST /api/datasource/report            生成「已确认版本 → 最新版本」的更新报告（函数级差异 + 后端文件映射）
  POST /api/datasource/porting/generate  AI 辅助移植：按报告生成后端文件替换建议（按 cache_key 缓存，零重复 token）
  POST /api/datasource/porting/apply     应用用户勾选的建议文件（三重校验 + 备份原文件，不自动重启）
"""
from fastapi import APIRouter, Body, HTTPException

from app.services import datasource_watch, porting_assist

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


@router.post("/porting/generate")
def porting_generate(body: dict = Body(default={})):
    """生成 AI 移植建议。body: {cache_key, refresh?}，与当前报告缓存不一致时报 502。"""
    try:
        return porting_assist.generate(
            str(body.get("cache_key") or ""),
            refresh=bool(body.get("refresh")),
        )
    except RuntimeError as exc:  # LLMError 也是 RuntimeError 子类
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/porting/apply")
def porting_apply(body: dict = Body(...)):
    """应用选中的建议文件。body: {cache_key, files[]}，校验失败整体报 400。"""
    files = body.get("files") if isinstance(body, dict) else None
    if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
        raise HTTPException(status_code=400, detail="files 必须是非空字符串数组")
    try:
        return porting_assist.apply(str(body.get("cache_key") or ""), files)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
