"""共享 SSL 上下文 —— 用 certifi 证书，规避 macOS 本地证书缺失问题。

macOS 上 python.org 安装的 Python 默认不信任系统证书，urllib 直连 HTTPS 会报
CERTIFICATE_VERIFY_FAILED。用 certifi（requests 的依赖，已安装）统一提供 CA 包。
"""
import ssl

import certifi

# 全局复用的 SSL 上下文（带 certifi CA 证书）
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
