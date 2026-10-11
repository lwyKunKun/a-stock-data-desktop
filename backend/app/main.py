"""FastAPI 主入口。

本地开发：uvicorn app.main:app --reload --port 8000
生产（阿里云）：gunicorn -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.report_routes import router as report_router
from app.api.data_routes import router as data_router
from app.api.datasource_routes import router as datasource_router

app = FastAPI(
    title="Stock App API",
    description="A股数据服务 —— 普通查询零 token，AI 分析按次调用",
    version="0.1.0",
)

# 允许前端跨域（PWA/Tauri 都需要）。生产环境应收紧 origins。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(report_router)
app.include_router(data_router)
app.include_router(datasource_router)


@app.get("/")
def root():
    return {"service": "stock-app", "docs": "/docs", "health": "/api/health"}
