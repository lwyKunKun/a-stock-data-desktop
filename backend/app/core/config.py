"""全局配置 —— 从 backend/.env 加载 DeepSeek 等敏感配置。

设计原则：
- API Key 绝不硬编码进代码，统一走 .env（已被 .gitignore 排除，不会提交）
- 用 python-dotenv 加载；缺失 Key 时 AI 分析端点会明确报错，而不是静默失败
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/.env 的绝对路径（本文件在 backend/app/core/config.py，往上三层到 backend/）
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH)


class Settings:
    """集中管理所有配置项，避免散落在各模块的 os.getenv。"""

    # ── LLM（AI 全维度分析，OpenAI 兼容接口，可整体替换平台）──
    # 任何提供 OpenAI 兼容 chat/completions 的平台都能接入：
    # 在 backend/.env 配 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 三项即可。
    # 未配置 LLM_* 时回退读取旧版 DEEPSEEK_* 变量，兼容已有 .env。
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL") or os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ── 全维度报告 ──
    REPORT_AI_CONCURRENCY: int = int(os.getenv("REPORT_AI_CONCURRENCY", "3"))
    REPORT_CHAPTER_MAX_TOKENS: int = int(os.getenv("REPORT_CHAPTER_MAX_TOKENS", "800"))
    REPORT_FINAL_MAX_TOKENS: int = int(os.getenv("REPORT_FINAL_MAX_TOKENS", "2500"))
    REPORT_AI_TIMEOUT: int = int(os.getenv("REPORT_AI_TIMEOUT", "180"))
    REPORT_AI_RETRIES: int = int(os.getenv("REPORT_AI_RETRIES", "2"))
    REPORT_TASK_STALE_SECONDS: int = int(os.getenv("REPORT_TASK_STALE_SECONDS", "600"))
    REPORT_AUTO_TRIGGER_DEFAULT: bool = os.getenv("REPORT_AUTO_TRIGGER", "0") == "1"

    # ── 报告发布 ──
    OBSIDIAN_SYNC_ENABLED: bool = os.getenv("OBSIDIAN_SYNC", "1") == "1"
    OBSIDIAN_VAULT_PATH: str = os.getenv(
        "OBSIDIAN_VAULT_PATH", "/Users/leiwanyue/Documents/Obsidian Vault"
    )
    STOCK_REVIEW_PUBLISH_ENABLED: bool = os.getenv("STOCK_REVIEW_PUBLISH", "1") == "1"
    STOCK_REVIEW_PATH: str = os.getenv("STOCK_REVIEW_PATH", "/Users/leiwanyue/stock-review")
    STOCK_REVIEW_DEPLOY_SCRIPT: str = os.getenv(
        "STOCK_REVIEW_DEPLOY_SCRIPT", "/Users/leiwanyue/stock-review/deploy.sh"
    )

    # ── 服务 ──
    PORT: int = int(os.getenv("PORT", "8000"))

    @property
    def llm_ready(self) -> bool:
        """AI 分析是否可用（Key 已配置）。"""
        return bool(self.LLM_API_KEY)

    @property
    def llm_provider_name(self) -> str:
        """平台显示名：LLM_PROVIDER 显式配置优先，否则从 base_url 推断。"""
        if self.LLM_PROVIDER:
            return self.LLM_PROVIDER
        host = self.LLM_BASE_URL.lower()
        if "deepseek" in host:
            return "DeepSeek"
        if "qianwen" in host:
            return "千问"
        if "aliyuncs" in host:
            return "阿里云百炼"
        if "openai" in host:
            return "OpenAI"
        return "自定义 LLM"


settings = Settings()
