"""运行时路径解析 —— 桌面打包与 Web 开发共用。

数据目录规则：
- 默认 backend/data/（Web 开发模式，行为与历史版本一致）
- 设置 APP_DATA_DIR 环境变量则指向该目录（Tauri 桌面端指向用户数据目录，
  因为 .app 包内只读，不能写缓存）
"""
import os
from pathlib import Path


def get_data_dir() -> Path:
    """返回数据根目录（reports/snapshots/tasks/索引库都在其下）。"""
    override = os.getenv("APP_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    # 本文件在 backend/app/core/paths.py，往上三层到 backend/
    return Path(__file__).resolve().parent.parent.parent / "data"


def is_packaged() -> bool:
    """是否以 PyInstaller 打包形态运行（桌面端）。

    PyInstaller 会把 sys.frozen 置为 True；同时要求 APP_DATA_DIR 已设置，
    否则数据目录会解析到包内临时路径，写缓存必然失败。
    """
    import sys
    return bool(getattr(sys, "frozen", False))
