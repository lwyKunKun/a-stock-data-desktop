"""OpenAI 兼容接口的 LLM 客户端。

平台由 backend/.env 的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 决定，
DeepSeek、千问 Token Plan、阿里云百炼、OpenAI 等任何兼容
chat/completions 的平台均可直接替换，本模块零平台相关逻辑。
"""
import time
from typing import Optional

import requests

from app.core.config import settings

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _retry_delay(attempt: int) -> float:
    return min(2 ** attempt, 8)


def chat(
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
) -> tuple[str, dict]:
    """调用 LLM，返回正文和 token 用量。"""
    if not settings.llm_ready:
        raise LLMError("未配置 LLM_API_KEY（或旧版 DEEPSEEK_API_KEY），请检查 backend/.env")

    request_timeout = timeout or getattr(settings, "REPORT_AI_TIMEOUT", 180)
    retry_count = retries if retries is not None else getattr(settings, "REPORT_AI_RETRIES", 2)
    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    provider = settings.llm_provider_name

    for attempt in range(retry_count + 1):
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=request_timeout,
            )
            if response.status_code in _RETRYABLE_STATUS and attempt < retry_count:
                time.sleep(_retry_delay(attempt))
                continue
            if not response.ok:
                body = response.text[:300]
                raise LLMError(
                    f"{provider} 调用失败: HTTP {response.status_code} | {body}",
                    response.status_code,
                )
            data = response.json()
            choices = data.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                raise LLMError(f"{provider} 返回结构缺少 choices[0].message")
            content = choices[0]["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise LLMError(f"{provider} 返回空内容")
            return content.strip(), data.get("usage") or {}
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < retry_count:
                time.sleep(_retry_delay(attempt))
                continue
            raise LLMError(f"{provider} 网络请求失败: {exc}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"{provider} 请求失败: {exc}") from exc

    raise LLMError(f"{provider} 调用失败")
