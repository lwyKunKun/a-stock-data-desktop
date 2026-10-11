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

    # ── DeepSeek（AI 全维度分析）──
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

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
    def deepseek_ready(self) -> bool:
        """AI 分析是否可用（Key 已配置）。"""
        return bool(self.DEEPSEEK_API_KEY)


settings = Settings()
