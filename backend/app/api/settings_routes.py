"""应用设置 —— 读写用户级配置（主要是 LLM 接入信息）。

设计原则：
- 永不返回完整 API Key：GET 只给脱敏掩码 + 是否已配置，PUT 接受的 Key 只落盘不外显
- 环境变量（含 .env）优先级高于用户配置文件，故设置页保存后若进程里仍有同名
  环境变量，以环境变量为准（Web 开发模式用 .env 配置时设置页改了不生效是预期行为）
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import (
    mask_key,
    settings,
    valid_base_url,
    write_user_config,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    """对外暴露的设置状态（Key 已脱敏）。"""

    llm_ready: bool
    llm_provider: str          # 平台显示名（Kimi / DeepSeek / ...）
    llm_base_url: str
    llm_model: str
    llm_temperature: float
    llm_key_masked: str = ""   # 已配置时返回掩码，未配置返回空串
    from_env: bool             # 当前生效值是否来自环境变量（为 True 时设置页改动不生效）
    sec_ready: bool
    sec_contact_masked: str = ""
    sec_from_env: bool


class SettingsUpdate(BaseModel):
    """设置页提交；所有字段可选，只更新提供的项。"""

    llm_api_key: str | None = Field(default=None, min_length=1, max_length=256)
    llm_base_url: str | None = Field(default=None, min_length=1, max_length=256)
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    sec_contact: str | None = Field(default=None, min_length=3, max_length=256)


def _current_from_env() -> bool:
    """生效的 Key 是否来自环境变量（优先级高于用户配置文件）。"""
    import os
    return bool(os.getenv("LLM_API_KEY"))


@router.get("", response_model=SettingsOut)
def get_settings():
    """读取当前生效的 LLM 设置（Key 脱敏）。"""
    return SettingsOut(
        llm_ready=settings.llm_ready,
        llm_provider=settings.llm_provider_name,
        llm_base_url=settings.LLM_BASE_URL,
        llm_model=settings.LLM_MODEL,
        llm_temperature=settings.LLM_TEMPERATURE,
        llm_key_masked=mask_key(settings.LLM_API_KEY),
        from_env=_current_from_env(),
        sec_ready=settings.sec_ready,
        sec_contact_masked=mask_key(settings.SEC_CONTACT),
        sec_from_env=bool(__import__("os").getenv("SEC_CONTACT")),
    )


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate):
    """保存 LLM 设置到用户配置文件；返回保存后生效值。"""
    updates: dict = {}
    if body.llm_api_key is not None:
        updates["LLM_API_KEY"] = body.llm_api_key.strip()
    if body.llm_base_url is not None:
        url = body.llm_base_url.strip()
        if not valid_base_url(url):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="LLM_BASE_URL 必须是 http(s):// 开头的合法 URL")
        updates["LLM_BASE_URL"] = url
    if body.llm_model is not None:
        updates["LLM_MODEL"] = body.llm_model.strip()
    if body.llm_temperature is not None:
        updates["LLM_TEMPERATURE"] = body.llm_temperature
    if body.sec_contact is not None:
        updates["SEC_CONTACT"] = body.sec_contact.strip()
    if not updates:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    write_user_config(updates)
    return get_settings()
