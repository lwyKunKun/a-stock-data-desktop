"""AI 分析服务 —— 调用 LLM（默认 Kimi，可在 .env 换成任意 OpenAI 兼容平台）生成个股全维度分析报告。

成本设计（这是整个项目「省 token」的核心环节）：
1. 输入是聚合器压缩后的快照文本（~1500 token），不是原始数据流
2. 当日同股报告落盘缓存（backend/data/reports/），重复点击直接读文件，0 成本
3. 强制刷新需显式传 refresh=true

走 OpenAI 兼容接口，直接用 requests 调用，不引入额外 SDK 依赖。
"""
import json
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.paths import get_data_dir
from app.services.aggregator import build_snapshot, snapshot_to_prompt_text
from app.services.llm_client import LLMError, chat

# 旧版短报告使用独立目录，避免覆盖十二章报告缓存。
REPORT_DIR = get_data_dir() / "reports" / "legacy"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── System Prompt：把投资分析框架写死，保证每次输出结构一致 ──
SYSTEM_PROMPT = """你是一位专业的A股投资分析师。基于用户提供的个股全维度数据快照，输出结构化分析报告。

分析框架（严格按此顺序）：
1. **一句话结论**：当前该股值得 关注/观望/回避，核心理由（不超过50字）
2. **估值判断**：用 前向PE → PE消化年限 → PEG 校验的框架判断贵贱（30x PE 是A股成长股估值锚点；PEG<1便宜、1~1.5合理、>1.5偏贵；负增长或无机构覆盖时说明估值框架失效，改用 PB/股息等锚）
3. **资金面**：当日主力 + 近5/20/60日资金趋势，判断主力是在流入还是流出
4. **题材与板块**：所属概念在当前市场的活跃度
5. **风险提示**：数据中的异常信号（僵尸报价/低覆盖度/资金流出等）+ 该股特有的风险

要求：
- 只基于给定数据说话，数据缺失就明说「数据未获取」，绝不编造数字
- 中文输出，用 Markdown，总长度控制在 600 字以内
- 结尾注明：本报告由 AI 基于公开数据生成，不构成投资建议
"""


def _report_path(code: str) -> Path:
    """当日报告文件路径：data/reports/2026-10-01_600519.md"""
    today = datetime.now().strftime("%Y-%m-%d")
    return REPORT_DIR / f"{today}_{code}.md"


def _load_cached_report(code: str):
    """读当日缓存报告，没有返回 None。"""
    p = _report_path(code)
    if p.exists():
        meta_path = p.with_suffix(".meta.json")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            meta = {}
        return {"code": code, "cached": True, "generated_at": meta.get("generated_at"),
                "model": meta.get("model"), "report": p.read_text(encoding="utf-8")}
    return None


def _save_report(code: str, report: str, model: str, usage: dict) -> None:
    """报告落盘 + 元信息（生成时间/模型/token用量），供前端展示与成本统计。"""
    p = _report_path(code)
    p.write_text(report, encoding="utf-8")
    p.with_suffix(".meta.json").write_text(json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": model, "usage": usage,
    }, ensure_ascii=False), encoding="utf-8")


def _call_llm(prompt_text: str) -> tuple[str, dict]:
    """调用 LLM chat/completions，返回 (报告文本, token用量)。"""
    return chat(
        SYSTEM_PROMPT,
        f"请分析以下个股数据快照：\n\n{prompt_text}",
        
        max_tokens=1500,
        timeout=120,
    )


def analyze(code: str, refresh: bool = False) -> dict:
    """全维度 AI 分析入口。

    refresh=False（默认）：当日已有报告直接返回缓存，0 token 成本
    refresh=True：强制重新生成
    """
    if not settings.llm_ready:
        return {"error": "未配置 LLM_API_KEY，请在「设置」页配置，或检查 backend/.env"}

    # 1. 缓存命中直接返回
    if not refresh:
        cached = _load_cached_report(code)
        if cached:
            return cached

    # 2. 抓全维度快照 → 压缩成 prompt 文本
    snapshot = build_snapshot(code)
    prompt_text = snapshot_to_prompt_text(snapshot)

    # 3. 调 LLM
    try:
        report, usage = _call_llm(prompt_text)
    except LLMError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"{settings.llm_provider_name} 调用失败: {e}"}

    # 4. 落盘缓存 + 返回
    _save_report(code, report, settings.LLM_MODEL, usage)
    return {
        "code": code, "cached": False,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": settings.LLM_MODEL,
        "usage": usage,   # {prompt_tokens, completion_tokens, total_tokens}
        "prompt_text": prompt_text,  # 调试用：让前端可以看到喂给 AI 的压缩数据
        "report": report,
    }
