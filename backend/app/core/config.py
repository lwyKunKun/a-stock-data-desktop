"""全局配置 —— 从 backend/.env 加载 LLM 等敏感配置。

设计原则：
- API Key 绝不硬编码进代码，统一走 .env（已被 .gitignore 排除，不会提交）
- 用 python-dotenv 加载；缺失 Key 时 AI 分析端点会明确报错，而不是静默失败
- 桌面打包形态没有 .env：LLM 配置改为「环境变量 > 用户配置文件」两级兜底，
  用户配置文件在数据目录下 config.json，由设置页读写
"""
import json
import os
import re
import threading
from pathlib import Path

from dotenv import load_dotenv

from app.core.paths import get_data_dir

# backend/.env 的绝对路径（本文件在 backend/app/core/config.py，往上三层到 backend/）
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH)

_user_config_lock = threading.RLock()
_user_config_cache: dict | None = None


def _user_config_path() -> Path:
    """用户级配置文件路径（设置页写入；桌面端位于用户数据目录）。"""
    return get_data_dir() / "config.json"


def _read_user_config() -> dict:
    """读取用户配置文件，带进程内缓存；文件缺失或损坏视为空配置。"""
    global _user_config_cache
    with _user_config_lock:
        if _user_config_cache is not None:
            return _user_config_cache
        cfg: dict = {}
        try:
            path = _user_config_path()
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg = raw
        except (OSError, json.JSONDecodeError):
            pass
        _user_config_cache = cfg
        return cfg


def write_user_config(updates: dict) -> dict:
    """合并写入用户配置文件（设置页调用），返回合并后的完整配置。"""
    global _user_config_cache
    with _user_config_lock:
        cfg = dict(_read_user_config())
        cfg.update(updates)
        path = _user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # 临时文件名带点前缀，与 report_task 的原子写残留清扫规则一致
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)  # 原子写入，避免中途崩溃留下半个文件
        finally:
            # 写入或 rename 失败时立即清理，不留给残留清扫兜底
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        _user_config_cache = cfg
        return cfg


def invalidate_user_config_cache() -> None:
    """外部直接改配置文件后调用（一般不需要，write_user_config 已同步缓存）。"""
    global _user_config_cache
    with _user_config_lock:
        _user_config_cache = None


def mask_key(key: str) -> str:
    """Key 脱敏：只露前 4 位与后 4 位，中间用 * 填充（前端展示用）。"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[0] + "***"
    return f"{key[:4]}***{key[-4:]}"


_URL_RE = re.compile(r"^https?://\S+$")


def valid_base_url(url: str) -> bool:
    """base_url 必须是 http(s) 开头且无空白，防止把奇怪字符串拼进请求 URL。"""
    return bool(_URL_RE.match(url.strip()))


class Settings:
    """集中管理所有配置项，避免散落在各模块的 os.getenv。"""

    # ── LLM（AI 全维度分析，OpenAI 兼容接口，可整体替换平台）──
    # 任何提供 OpenAI 兼容 chat/completions 的平台都能接入。
    # 配置来源两级兜底：进程环境变量（含 .env）优先，其次用户配置文件。
    # 当前使用 Kimi For Coding 订阅（api.kimi.com/coding/v1）。

    @property
    def LLM_PROVIDER(self) -> str:
        return os.getenv("LLM_PROVIDER") or str(_read_user_config().get("LLM_PROVIDER", ""))

    @property
    def LLM_API_KEY(self) -> str:
        return os.getenv("LLM_API_KEY") or str(_read_user_config().get("LLM_API_KEY", ""))

    @property
    def LLM_BASE_URL(self) -> str:
        return os.getenv("LLM_BASE_URL") or str(
            _read_user_config().get("LLM_BASE_URL", "https://api.kimi.com/coding/v1")
        )

    @property
    def LLM_MODEL(self) -> str:
        return os.getenv("LLM_MODEL") or str(_read_user_config().get("LLM_MODEL", "kimi-k2-0711-preview"))

    @property
    def LLM_TEMPERATURE(self) -> float:
        raw = os.getenv("LLM_TEMPERATURE")
        if raw is None:
            raw = _read_user_config().get("LLM_TEMPERATURE")
        try:
            return float(raw) if raw is not None else 0.3
        except (TypeError, ValueError):
            return 0.3

    # ── 全维度报告 ──
    REPORT_AI_CONCURRENCY: int = int(os.getenv("REPORT_AI_CONCURRENCY", "3"))
    REPORT_CHAPTER_MAX_TOKENS: int = int(os.getenv("REPORT_CHAPTER_MAX_TOKENS", "800"))
    REPORT_FINAL_MAX_TOKENS: int = int(os.getenv("REPORT_FINAL_MAX_TOKENS", "2500"))
    REPORT_AI_TIMEOUT: int = int(os.getenv("REPORT_AI_TIMEOUT", "180"))
    REPORT_AI_RETRIES: int = int(os.getenv("REPORT_AI_RETRIES", "2"))
    REPORT_TASK_STALE_SECONDS: int = int(os.getenv("REPORT_TASK_STALE_SECONDS", "600"))

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
        if "kimi" in host or "moonshot" in host:
            return "Kimi"
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
