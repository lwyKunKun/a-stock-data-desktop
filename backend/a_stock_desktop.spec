# -*- mode: python ; coding: utf-8 -*-
"""桌面端 sidecar 打包配置 —— 把 FastAPI 后端打成单个可执行文件。

产物供 Tauri 作为 sidecar 拉起（frontend/src-tauri/binaries/），
Tauri 启动时注入 PORT / APP_DATA_DIR 环境变量。

构建（在 backend/ 目录下）：
    .venv/bin/pyinstaller a_stock_desktop.spec --clean --noconfirm

验证产物可独立运行（数据目录隔离到临时目录）：
    APP_DATA_DIR=$(mktemp -d) PORT=18099 dist/a_stock_desktop/a_stock_desktop &
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
# 数据请求相关： certifi 证书（本机 python.org Python 不信任系统证书，代码用 certifi.where()）
hiddenimports += ["certifi"]
# uvicorn 的协议/循环实现按需动态导入，显式收集避免打包后缺模块
hiddenimports += collect_submodules("uvicorn")
# 后端 app 包全量收集：数据源模块里有函数内惰性 import（pandas 等），
# 静态分析追踪不到，缺一个运行时就是 ModuleNotFoundError
hiddenimports += collect_submodules("app")

a = Analysis(
    ["desktop_main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="a_stock_desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 无控制台窗口；日志由 Tauri 捕获
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
)
