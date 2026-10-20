"""FastAPI 主入口。

本地开发：uvicorn app.main:app --reload --port 8000
生产（阿里云）：gunicorn -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:8000
桌面端：由 Tauri 拉起 PyInstaller 产物（desktop_main.py），见 backend/a_stock_desktop.spec
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.report_routes import router as report_router
from app.api.data_routes import router as data_router
from app.api.datasource_routes import router as datasource_router
from app.api.settings_routes import router as settings_router
from app.api.us_routes import router as us_router
from app.api.us_report_routes import router as us_report_router

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
app.include_router(settings_router)
app.include_router(us_router)
app.include_router(us_report_router)


# ── 桌面端静态托管 ──
# Tauri 壳内 WebView 直接加载本服务（http://127.0.0.1:端口/），
# 前端相对路径 /api 免改造；SERVE_STATIC_DIR 由 Tauri 启动 sidecar 时注入，
# 指向打包资源里的 dist/。Web 开发模式不设置该变量，行为不变。
_serve_dir = os.getenv("SERVE_STATIC_DIR", "").strip()
if _serve_dir:
    from fastapi.staticfiles import StaticFiles

    # 挂在路由表最末尾，/api 等接口优先匹配；「/」本身也交给 StaticFiles
    # 的 html=True 处理（自动回退 index.html），故不再注册 JSON 根路由
    app.mount("/", StaticFiles(directory=_serve_dir, html=True), name="desktop")


if not _serve_dir:

    @app.get("/")
    def root():
        return {"service": "stock-app", "docs": "/docs", "health": "/api/health"}
