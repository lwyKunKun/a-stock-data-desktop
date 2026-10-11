"""API 路由 —— 数据查询（零 token）+ AI 分析（按次调用 DeepSeek）。

端点：
  GET /api/health                 健康检查
  GET /api/quote?codes=600519,000300   实时行情（腾讯，可批量）
  GET /api/valuation/{code}       完整估值（服务端出结论）
  GET /api/fundflow/{code}        资金流（分钟级 + 日级聚合）
  GET /api/concept/{code}         板块/概念归属
  GET /api/snapshot/{code}        全维度快照（个股详情页数据底座）
  GET /api/ai_analysis/{code}     AI 全维度分析（DeepSeek，当日缓存，refresh=true 强刷）
  POST /api/cache/clear           清缓存（管理）
"""
from fastapi import APIRouter, HTTPException, Query

from app.core.ticker import norm_ticker
from app.core import cache
from app.datasources.tencent import tencent_quote
from app.datasources.eastmoney import fund_flow_minute, fund_flow_daily, concept_blocks
from app.services.valuation import full_valuation
from app.services.aggregator import build_snapshot
from app.services.ai_analyst import analyze

router = APIRouter(prefix="/api")


def _safe_code(code: str, stock_only: bool = False) -> str:
    try:
        return norm_ticker(code, stock_only=stock_only)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
def health():
    return {"status": "ok", "service": "stock-app", "phase": "P1"}


@router.get("/quote")
def quote(codes: str = Query(..., description="逗号分隔，如 600519,000300,510300")):
    """实时行情（腾讯，不封 IP，可批量）。"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(400, "codes 不能为空")
    try:
        return tencent_quote(code_list)
    except Exception as e:
        raise HTTPException(502, f"行情获取失败: {e}")


@router.get("/valuation/{code}")
def valuation(code: str):
    """完整估值 —— 前向PE/PEG/消化年限，服务端直接出结论。"""
    c = _safe_code(code, stock_only=True)
    return full_valuation(c)


@router.get("/fundflow/{code}")
def fundflow(code: str):
    """资金流 —— 分钟级（当日）+ 日级（5/20/60日聚合）。"""
    c = _safe_code(code)
    return {"minute": fund_flow_minute(c), "daily": fund_flow_daily(c)}


@router.get("/concept/{code}")
def concept(code: str):
    """个股所属板块/概念归属。"""
    c = _safe_code(code)
    return concept_blocks(c)


@router.get("/snapshot/{code}")
def snapshot(code: str):
    """全维度快照 —— 个股详情页的数据底座（并发抓取，零 token）。"""
    c = _safe_code(code)
    return build_snapshot(c)


@router.get("/ai_analysis/{code}")
def ai_analysis(code: str, refresh: bool = Query(False, description="true=强制重新生成")):
    """AI 全维度分析 —— 调 LLM（.env 可换平台）生成报告。

    当日同股默认读缓存（0 成本）；refresh=true 强制重新生成。
    """
    c = _safe_code(code, stock_only=True)
    result = analyze(c, refresh=refresh)
    if "error" in result:
        # Key 未配置属服务端配置问题(500)，其余按上游失败(502)
        raise HTTPException(500 if "API_KEY" in result["error"] else 502,
                            result["error"])
    return result


@router.post("/cache/clear")
def clear_cache(prefix: str = Query(None)):
    n = cache.cache_clear(prefix)
    return {"cleared": n}
