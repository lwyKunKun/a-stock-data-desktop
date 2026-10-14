#!/bin/bash
# 启动桌面端（与 Web 开发模式共用 backend/data 数据目录）
#
# 原理：通过环境变量 DESKTOP_DATA_DIR 告知桌面壳把业务数据（报告缓存、
# 快照、任务状态、索引库）写到项目 backend/data/，与 uvicorn + npm run dev
# 的 Web 端完全互通。
# 当前版本桌面壳在未设此变量时，会自动探测 ~/a-stock-data-desktop/backend/data
# 并与之共用，所以直接双击 .app 也能数据互通；本脚本保留作为显式指定
# 数据目录的启动方式（例如项目目录不在默认位置时）。
#
# 注意：用 open 命令启动 .app 无法传递环境变量，这里直接执行二进制。

set -e

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

APP="frontend/src-tauri/target/release/bundle/macos/Palantir · 个人投研全景工作台.app"
BIN="$APP/Contents/MacOS/stock-app-desktop"

export DESKTOP_DATA_DIR="$PWD/backend/data"
mkdir -p "$DESKTOP_DATA_DIR"

if [ ! -x "$BIN" ]; then
    echo "未找到桌面端二进制：$BIN"
    echo "请先打包：cd frontend && cargo tauri build --bundles app,dmg"
    exit 1
fi

# 后台启动，脚本本身退出
nohup "$BIN" >/dev/null 2>&1 &
echo "桌面端已启动，数据目录：$DESKTOP_DATA_DIR"
