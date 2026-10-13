"""AI 辅助移植 —— 把上游 a-stock-data 的更新落成后端移植代码建议。

与「一键更新报告」（零 token 只出报告）衔接：报告告诉用户「改了哪些函数、影响哪些后端文件」，
本模块再进一步调 LLM 生成「后端文件的完整替换内容」，用户在页面确认后 apply 才落盘。

设计原则：
1. 生成与应用分离：AI 只产建议 JSON，人在页面勾选确认后 apply 才写文件
2. 按报告 cache_key 磁盘缓存建议，同一版本区间重复点击零 token
3. 应用三重校验：白名单（报告 backend_impacts）→ 路径解析后必须位于 backend/app/ 内
   → 源文件 sha256 与建议生成时一致（防止报告生成后文件被改动）
4. 每次应用先把原文件按时间戳备份到 data/patch_backups/，不自动清理、不自动重启

LLM 输出要求严格 JSON（每文件一份完整替换内容），单文件语法用 compile() 试编译校验，
解析失败的文件降级进 skipped，不整体失败。
"""
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from app.core.config import settings
from app.core.paths import get_data_dir, is_packaged
from app.services import datasource_watch
from app.services.llm_client import chat

# 后端根目录（backend/）；报告里 backend_file 形如 "app/core/ticker.py"，相对此目录。
# 桌面打包形态取数代码在 PyInstaller 包内，无源码文件可改写，AI 辅助移植不可用。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
APP_ROOT = BACKEND_DIR / "app"

# 打包形态下 porting 功能直接禁用（raise 语义在各入口函数检查）
def _ensure_source_available() -> None:
    if is_packaged():
        raise RuntimeError("桌面打包版本内嵌取数源码，不支持 AI 辅助移植；请在开发模式下使用")

SUGGEST_DIR = datasource_watch.DATA_DIR / "porting_suggestions"
BACKUP_DIR = datasource_watch.DATA_DIR / "patch_backups"

# 上游代码全部内嵌在 SKILL.md，测试在 tests/ 下；README/CHANGELOG 对移植无参考价值，不进 prompt
PORTING_PATCH_FILES = ("SKILL.md",)

MAX_OUTPUT_TOKENS = 16000  # 输出是完整文件替换内容，默认 800 必截断
GEN_TIMEOUT = 600

# cache_key 形如 "abc123def456...789abc012345"（sha 前 12 位 + ... + 后段），限制字符集防路径穿越
_CACHE_KEY_RE = re.compile(r"^[\w.\-]+$")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$")

_lock = threading.Lock()


# ── 基础工具 ──

def _atomic_write_text(path: Path, content: str) -> None:
    """tmp 文件 + os.replace 原子写入，避免中途崩溃留下半个文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_cache_key(cache_key: str) -> None:
    if not cache_key or not _CACHE_KEY_RE.match(cache_key):
        raise RuntimeError("无效的 cache_key")


def _resolve_backend_file(rel: str) -> Path:
    """把报告的 backend_file 解析成绝对路径，并约束必须位于 backend/app/ 内。"""
    target = (BACKEND_DIR / rel).resolve()
    if not str(target).startswith(str(APP_ROOT.resolve()) + os.sep):
        raise RuntimeError(f"非法文件路径：{rel}")
    if target.suffix != ".py":
        raise RuntimeError(f"只允许改写 .py 文件：{rel}")
    return target


# ── 上游完整 diff 拉取 ──

def _split_patch_by_file(text: str) -> dict:
    """把 concatenated 的 .patch 文本按文件拆成 {文件名: 段落列表}。"""
    sections: dict = {}
    current: Optional[str] = None
    for line in text.splitlines(keepends=True):
        match = _DIFF_HEADER_RE.match(line)
        if match:
            current = match.group(2)
            sections.setdefault(current, [])
        if current is not None:
            sections[current].append(line)
    return sections


def _fetch_full_patches(base: str, head: str) -> dict:
    """拉取版本区间内上游代码文件的完整 diff。

    报告里的 patch_excerpt 只保留 40 行，移植需要全文。优先用 compare API 的
    files[].patch；单文件改动过大被 GitHub 省略 patch 字段时，退回逐 commit 拉
    .patch 文本按文件拼接。只保留 SKILL.md 与 tests/ 下的内容（代码与测试），
    README/CHANGELOG 不进 prompt。
    """
    try:
        comparison = datasource_watch._fetch_json(
            f"{datasource_watch.GITHUB_COMPARE_API}/{base}...{head}"
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"无法获取上游差异：{exc}")

    patches: dict = {}
    missing: list = []
    for item in comparison.get("files") or []:
        name = item.get("filename", "")
        if not _is_porting_relevant(name):
            continue
        if item.get("patch"):
            patches[name] = item["patch"]
        else:
            missing.append(name)

    if missing:
        # GitHub 对超大 diff 会省略 patch 字段，逐 commit 的 .patch 是完整口径
        combined: dict = {}
        for commit in comparison.get("commits") or []:
            sha = commit.get("sha")
            if not sha:
                continue
            try:
                resp = requests.get(
                    f"https://github.com/{datasource_watch.REPO}/commit/{sha}.patch",
                    timeout=datasource_watch.REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
            except requests.RequestException:
                continue
            for name, section in _split_patch_by_file(resp.text).items():
                combined.setdefault(name, []).append("".join(section))
        for name in missing:
            if name in combined:
                patches[name] = "".join(combined[name])

    if not patches:
        raise RuntimeError("上游本次更新未涉及 SKILL.md 代码，无需 AI 移植")
    return patches


def _is_porting_relevant(filename: str) -> bool:
    """只有 SKILL.md（内嵌全部上游代码）与 tests/（预期行为参考）对移植有用。"""
    return filename == "SKILL.md" or filename.startswith("tests/")


# ── prompt 组装 ──

_SYSTEM_PROMPT = """你是后端代码移植专家。用户有一个 A 股数据桌面应用，其后端取数代码是从开源项目 a-stock-data（全部代码内嵌在单文件 SKILL.md 中）移植重写来的，与上游代码不逐行对应。

任务：根据上游更新 diff，为后端移植文件生成「完整替换内容」，把上游修复/变更的语义合入后端。

铁律：
1. 只输出严格 JSON，不要输出 JSON 以外的任何文字，不要用 markdown 代码围栏包裹整体输出。
2. 只修改输入中列出的后端文件：不新增文件、不改动其他文件、不新增第三方库 import（只允许文件已有的依赖与标准库）。
3. 后端是移植重写而非上游副本：保留本地既有改造（配置注入、错误处理风格、中文注释、已有函数签名与返回结构），只合入上游变更的语义。若上游某处变更在后端对应位置早已等价甚至更优（例如返回值语义本端早已正确），保持后端现状，说明理由即可，不要照搬上游。
4. 输出结构（顶层对象）：
{"files":[{"backend_file":"输入中给出的路径","functions":["受影响的函数名"],"explanation":"一句话说明改了什么、为什么","confidence":"high|medium|low","full_content":"替换后的完整 Python 文件内容"}],"skipped":[{"backend_file":"...","reason":"无法安全移植的原因"}]}
5. backend_file 必须与输入中给出的路径完全一致；full_content 必须是完整可运行的文件，从第一个 import/docstring 开始到文件末尾，不得用省略号或「其余不变」占位。
6. 无法安全移植的文件不要放进 files，放进 skipped 并说明原因。
7. 说明与注释一律用中文。"""


def _build_prompt(report: dict, patches: dict, sources: dict) -> str:
    """组装 user prompt：提交摘要 + 受影响文件清单 + 后端当前完整内容 + 上游完整 diff。"""
    lines = [
        f"上游仓库：{datasource_watch.REPO}（代码全部内嵌于 SKILL.md）",
        f"版本区间：{report['base_sha'][:12]} → {report['head_sha'][:12]}",
        "",
        "提交列表：",
    ]
    for commit in report.get("commits") or []:
        lines.append(
            f"- {commit['sha'][:12]} {commit['message']}"
            f"（{commit.get('author') or '未知'} · {commit.get('date', '')[:10]}）"
        )
    lines += ["", "后端受影响的移植文件与涉及函数："]
    for impact in report.get("backend_impacts") or []:
        lines.append(f"- {impact['backend_file']}：{'、'.join(impact['functions'])}")

    lines += ["", "=== 后端文件当前完整内容 ==="]
    for rel, source in sources.items():
        lines += [f"### {rel}（源文件 sha256: {source['sha256']}）", source["content"]]

    lines += ["", "=== 上游完整 diff ==="]
    for name, patch in patches.items():
        lines += [f"### {name}", patch]

    return "\n".join(lines)


def _read_backend_sources(impacts: list) -> dict:
    """读取 backend_impacts 对应的后端文件完整内容与 sha256。"""
    sources: dict = {}
    for impact in impacts:
        rel = impact["backend_file"]
        try:
            target = _resolve_backend_file(rel)
        except RuntimeError:
            continue
        if not target.exists():
            continue
        data = target.read_bytes()
        sources[rel] = {
            "content": data.decode("utf-8"),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    if not sources:
        raise RuntimeError("后端移植文件均不存在，无法生成建议")
    return sources


# ── 建议解析校验 ──

def _parse_suggestions(raw: str, allowed_files: set, file_hashes: dict) -> dict:
    """解析 AI 输出的 JSON，逐文件校验，非法条目降级 skipped。"""
    text = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 输出 JSON 解析失败：{exc}")
    if not isinstance(data, dict):
        raise RuntimeError("AI 输出 JSON 顶层必须是对象")

    raw_files = data.get("files", [])
    raw_skipped = data.get("skipped", [])
    if not isinstance(raw_files, list):
        raise RuntimeError("AI 输出的 files 必须是数组")
    if not isinstance(raw_skipped, list):
        raise RuntimeError("AI 输出的 skipped 必须是数组")

    files_out, skipped = [], []
    for item in raw_files:
        if not isinstance(item, dict):
            skipped.append({"backend_file": "", "reason": "文件建议不是对象，已忽略"})
            continue
        name = item.get("backend_file")
        content = item.get("full_content")
        if name not in allowed_files:
            skipped.append({"backend_file": str(name), "reason": "不在报告的移植范围内，已忽略"})
            continue
        if not isinstance(content, str) or not content.strip():
            skipped.append({"backend_file": name, "reason": "缺少 full_content"})
            continue
        try:
            compile(content, name, "exec")
        except SyntaxError as exc:
            skipped.append({"backend_file": name, "reason": f"语法错误：{exc}"})
            continue
        confidence = item.get("confidence")
        functions = item.get("functions")
        files_out.append({
            "backend_file": name,
            "functions": functions if isinstance(functions, list) else [],
            "explanation": item.get("explanation") if isinstance(item.get("explanation"), str) else "",
            "confidence": confidence if confidence in ("high", "medium", "low") else "medium",
            "full_content": content,
            # 记录生成时的源文件哈希，apply 时强校验，防止建议过期
            "source_sha256": file_hashes.get(name, ""),
        })
    for item in raw_skipped:
        if not isinstance(item, dict):
            skipped.append({"backend_file": "", "reason": "跳过项不是对象，已忽略"})
            continue
        skipped.append({
            "backend_file": str(item.get("backend_file") or ""),
            "reason": str(item.get("reason") or ""),
        })
    if not files_out:
        raise RuntimeError("AI 没有产出可应用的建议")
    return {"files": files_out, "skipped": skipped}


# ── 对外入口 ──

def load(cache_key: str) -> Optional[dict]:
    """读建议缓存；文件缺失或损坏返回 None。"""
    try:
        _check_cache_key(cache_key)
        path = SUGGEST_DIR / f"{cache_key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def generate(cache_key: str, refresh: bool = False) -> dict:
    """生成移植建议。流程：校验报告 → 拉完整 diff → 读后端源文件 → LLM → 解析落盘。

    同一 cache_key 重复调用直接返回缓存（零 token），refresh=True 强制重新生成。
    """
    if not settings.llm_ready:
        raise RuntimeError("未配置 LLM_API_KEY，请在设置页或 backend/.env 中配置")
    _ensure_source_available()
    _check_cache_key(cache_key)
    with _lock:
        report = datasource_watch._load_report_cache()
        if not report or report.get("cache_key") != cache_key:
            raise RuntimeError("更新报告已过期，请重新生成更新报告后再试")

        if not refresh:
            cached = load(cache_key)
            if cached:
                return cached

        impacts = report.get("backend_impacts") or []
        if not impacts:
            raise RuntimeError("本次更新没有映射到后端移植文件，无需 AI 移植")

        patches = _fetch_full_patches(report["base_sha"], report["head_sha"])
        sources = _read_backend_sources(impacts)
        prompt = _build_prompt(report, patches, sources)

        raw, usage = chat(
            _SYSTEM_PROMPT,
            prompt,
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=GEN_TIMEOUT,
            retries=1,
        )
        parsed = _parse_suggestions(
            raw,
            {i["backend_file"] for i in impacts},
            {rel: s["sha256"] for rel, s in sources.items()},
        )
        suggestion = {
            "cache_key": cache_key,
            "base_sha": report["base_sha"],
            "head_sha": report["head_sha"],
            "model": settings.LLM_MODEL,
            "usage": usage,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            **parsed,
        }
        _atomic_write_text(
            SUGGEST_DIR / f"{cache_key}.json",
            json.dumps(suggestion, ensure_ascii=False, indent=2),
        )
        return suggestion


def apply(cache_key: str, files: list) -> dict:
    """应用用户勾选的建议文件：三重校验 → 备份 → 原子写入。

    只写通过全部校验的文件；被拒绝的进 rejected 并带原因，不中断其他文件。
    """
    _ensure_source_available()
    _check_cache_key(cache_key)
    with _lock:
        suggestion = load(cache_key)
        if not suggestion:
            raise RuntimeError("建议不存在或已过期，请先生成 AI 辅助移植建议")

        report = datasource_watch._load_report_cache()
        allowed: set = set()
        if report and report.get("cache_key") == cache_key:
            allowed = {i["backend_file"] for i in report.get("backend_impacts") or []}
        by_file = {f["backend_file"]: f for f in suggestion.get("files") or []}

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        applied, rejected, backups = [], [], []
        for name in files:
            entry = by_file.get(name)
            if entry is None:
                rejected.append({"backend_file": name, "reason": "不在建议列表中"})
                continue
            if name not in allowed:
                rejected.append({"backend_file": name, "reason": "不在当前报告的移植范围内"})
                continue
            try:
                target = _resolve_backend_file(name)
            except RuntimeError as exc:
                rejected.append({"backend_file": name, "reason": str(exc)})
                continue
            if not target.exists():
                rejected.append({"backend_file": name, "reason": "文件不存在"})
                continue
            if _sha256_of(target) != entry.get("source_sha256"):
                rejected.append({
                    "backend_file": name,
                    "reason": "文件在建议生成后被修改过，请重新生成建议",
                })
                continue
            try:
                compile(entry["full_content"], name, "exec")
            except SyntaxError as exc:
                rejected.append({"backend_file": name, "reason": f"语法错误：{exc}"})
                continue

            backup = BACKUP_DIR / timestamp / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(target.read_bytes())
            _atomic_write_text(target, entry["full_content"])
            applied.append(name)
            backups.append({"backend_file": name, "backup_path": str(backup)})

        return {
            "applied": applied,
            "rejected": rejected,
            "backups": backups,
            "restart_hint": "补丁已落盘，重启后端服务后生效" if applied else "",
        }
