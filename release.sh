#!/bin/bash
# ================================================
# a-stock-data-desktop 安装包发布脚本
# 把 releases/vX.Y.Z/ 下的 dmg 上传到阿里云 ECS，
# 通过 nginx 默认站点（/var/www/html/releases/）对外提供下载
# 用法: bash release.sh v0.5.1
# ================================================
set -e

cd "$(dirname "$0")"

VERSION="${1:?用法: bash release.sh vX.Y.Z（如 v0.5.1）}"
SERVER="aliyun-stock"
LOCAL_DIR="releases/${VERSION}"

if [ ! -d "${LOCAL_DIR}" ]; then
    echo "错误：本地目录 ${LOCAL_DIR} 不存在，请先 cargo tauri build 并归档 dmg"
    exit 1
fi

DMG=$(ls "${LOCAL_DIR}"/*.dmg 2>/dev/null | head -1)
if [ -z "${DMG}" ]; then
    echo "错误：${LOCAL_DIR} 下没有 .dmg 文件"
    exit 1
fi
DMG_NAME=$(basename "${DMG}")

echo "==> 上传 ${DMG_NAME} 到 ${SERVER}:/var/www/html/releases/${VERSION}/"
ssh "${SERVER}" "mkdir -p /var/www/html/releases/${VERSION}"
scp "${DMG}" "${SERVER}:/var/www/html/releases/${VERSION}/"

echo "==> 校验服务器端 sha256"
LOCAL_SHA=$(shasum -a 256 "${DMG}" | awk '{print $1}')
REMOTE_SHA=$(ssh "${SERVER}" "sha256sum /var/www/html/releases/${VERSION}/${DMG_NAME}" | awk '{print $1}')
if [ "${LOCAL_SHA}" != "${REMOTE_SHA}" ]; then
    echo "错误：sha256 不一致！本地 ${LOCAL_SHA} vs 服务器 ${REMOTE_SHA}"
    exit 1
fi

ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "${DMG_NAME}")
URL="http://47.109.108.159/releases/${VERSION}/${ENCODED}"

echo ""
echo "发布完成："
echo "  公网直链: ${URL}"
echo "  sha256:   ${LOCAL_SHA}"
echo ""
echo "下一步：把直链写入 CHANGELOG.md 的 ${VERSION} 条目"
