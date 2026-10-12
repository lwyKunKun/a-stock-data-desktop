"""数据源仓库版本监控 —— 跟踪上游 GitHub 仓库 simonlin1212/a-stock-data 的新提交。

原理：
- 通过 GitHub API 查询默认分支最新 commit（未认证限流 60 次/小时，故检查结果缓存 10 分钟）
- 本地状态持久化到 backend/data/datasource_version.json：
  acknowledged_sha  用户已确认看到的 commit（"知道了"后更新）
  last_seen_sha     最近一次检查到的上游最新 commit
- update_available = last_seen_sha != acknowledged_sha
"""
import json
import re
import threading
import time
from pathlib import Path
from typing import Optional

import requests

REPO = "simonlin1212/a-stock-data"
GITHUB_COMMITS_API = f"https://api.github.com/repos/{REPO}/commits"
GITHUB_COMPARE_API = f"https://api.github.com/repos/{REPO}/compare"
COMMITS_PAGE = f"https://github.com/{REPO}/commits"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STATE_PATH = DATA_DIR / "datasource_version.json"
REPORT_CACHE_PATH = DATA_DIR / "datasource_report.json"
CHECK_CACHE_SECONDS = 600  # GitHub 未认证限流 60 次/小时，10 分钟缓存足够保守
REQUEST_TIMEOUT = 10
PATCH_EXCERPT_LINES = 40  # 报告中每个文件最多展示的补丁行数
REPORT_FORMAT_VERSION = 2  # 映射规则变化时递增，避免沿用缺字段/缺影响文件的旧缓存

_lock = threading.Lock()
_state_cache: Optional[dict] = None
_last_check_at: float = 0.0
_last_latest: Optional[dict] = None  # 最近一次成功查到的上游 commit
_last_check_error: Optional[str] = None


def _load_state() -> dict:
    """读取本地状态文件；文件缺失或损坏时返回初始状态。"""
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {"acknowledged_sha": None, "last_seen_sha": None, "last_seen_at": None}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _query_latest_commit() -> dict:
    """请求 GitHub API 拿默认分支最新 commit；失败抛异常。"""
    resp = requests.get(
        GITHUB_COMMITS_API,
        params={"per_page": 1},
        headers={"Accept": "application/vnd.github+json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    commits = resp.json()
    if not commits:
        raise RuntimeError("上游仓库暂无提交记录")
    item = commits[0]
    commit = item.get("commit", {})
    return {
        "sha": item.get("sha", ""),
        "message": (commit.get("message") or "").splitlines()[0],
        "date": (commit.get("committer") or {}).get("date", ""),
        "author": (commit.get("author") or {}).get("name", ""),
        "url": item.get("html_url", COMMITS_PAGE),
    }


def _fetch_json(url: str) -> dict:
    """请求 GitHub API 并返回 JSON；失败抛 requests.RequestException。"""
    resp = requests.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(")


def _backend_function_index() -> dict:
    """扫描后端移植区的函数定义。

    大部分上游数据源函数位于 app/core、app/datasources；估值公式单独移植到
    app/services/valuation.py，也必须纳入映射，否则 PE/PEG 修复会被误报为未接入。
    返回 {函数名: 相对文件路径}。
    """
    app_dir = Path(__file__).resolve().parent.parent
    index: dict = {}
    py_files = []
    for sub in ("core", "datasources"):
        py_files.extend(sorted((app_dir / sub).glob("*.py")))
    py_files.append(app_dir / "services" / "valuation.py")
    for py_file in py_files:
        if py_file.parent.name == "services":
            rel = f"app/services/{py_file.name}"
        else:
            rel = f"app/{py_file.parent.name}/{py_file.name}"
        try:
            for line in py_file.read_text(encoding="utf-8").splitlines():
                match = _DEF_RE.match(line)
                if match:
                    index.setdefault(match.group(1), rel)
        except OSError:
            continue
    return index


def _extract_changed_functions(files: list) -> tuple:
    """从 compare API 的文件补丁里提取新增/修改的顶层函数定义。

    返回 (变更函数集合, 每文件补丁摘要列表)。
    补丁摘要截断到 PATCH_EXCERPT_LINES 行，避免大版本跳跃撑爆响应。
    """
    changed: set = set()
    summaries = []
    for item in files:
        patch = item.get("patch") or ""
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                match = _DEF_RE.match(line[1:])
                if match:
                    changed.add(match.group(1))
        excerpt_lines = patch.splitlines()[:PATCH_EXCERPT_LINES]
        summaries.append({
            "filename": item.get("filename", ""),
            "status": item.get("status", ""),
            "additions": item.get("additions", 0),
            "deletions": item.get("deletions", 0),
            "patch_excerpt": "\n".join(excerpt_lines),
            "truncated": len(patch.splitlines()) > PATCH_EXCERPT_LINES,
        })
    return changed, summaries


def _ensure_fresh() -> None:
    """必要时重新检查上游（带 10 分钟缓存）。必须持锁调用。"""
    global _state_cache, _last_check_at, _last_latest, _last_check_error
    if time.time() - _last_check_at < CHECK_CACHE_SECONDS and _state_cache is not None:
        return
    _last_check_at = time.time()
    try:
        _last_latest = _query_latest_commit()
        _last_check_error = None
        state = _load_state()
        if state.get("last_seen_sha") != _last_latest["sha"]:
            state["last_seen_sha"] = _last_latest["sha"]
            state["last_seen_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _save_state(state)
        _state_cache = state
    except requests.RequestException as exc:
        _last_check_error = f"无法连接 GitHub：{exc}"


def get_status() -> dict:
    """前端轮询入口：返回完整数据源版本状态。"""
    global _state_cache, _last_check_at, _last_latest, _last_check_error
    with _lock:
        _ensure_fresh()
        state = _state_cache or _load_state()
        latest = _last_latest
        if latest is None:
            # 缓存过期且本次检查失败时，退回状态文件里的 last_seen
            seen = state.get("last_seen_sha")
            latest = {"sha": seen, "message": None, "date": None,
                      "author": None, "url": COMMITS_PAGE} if seen else None
        acknowledged = state.get("acknowledged_sha")
        update_available = bool(
            latest and latest.get("sha") and latest.get("sha") != acknowledged
        )
        return {
            "repo": REPO,
            "commits_url": COMMITS_PAGE,
            "latest": latest,
            "acknowledged_sha": acknowledged,
            "update_available": update_available,
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_last_check_at)),
            "check_ok": _last_check_error is None,
            "error": _last_check_error,
        }


def acknowledge() -> dict:
    """用户确认已知悉更新：把当前上游 sha 记为已确认，横幅不再提示。"""
    global _state_cache
    with _lock:
        _ensure_fresh()
        state = _load_state()
        if _last_latest:
            state["acknowledged_sha"] = _last_latest["sha"]
        elif state.get("last_seen_sha"):
            state["acknowledged_sha"] = state["last_seen_sha"]
        _save_state(state)
        _state_cache = state
    return get_status()


def _load_report_cache() -> Optional[dict]:
    try:
        if REPORT_CACHE_PATH.exists():
            return json.loads(REPORT_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def build_update_report() -> dict:
    """生成「已确认版本 → 最新版本」的更新报告。

    数据来自 GitHub compare API（一次请求拿提交列表 + 文件级补丁），
    再扫描后端函数索引，把变更的函数映射回移植文件。
    结果按 base...head 键做磁盘缓存，同一版本区间重复点击不重复请求。

    无确认基线（首次使用）时退化为对比最新提交的父提交，只报告最近一次变更。
    """
    with _lock:
        _ensure_fresh()
        latest = _last_latest
        if not latest or not latest.get("sha"):
            raise RuntimeError("尚未获取到上游版本信息，请稍后再试")
        head = latest["sha"]
        state = _load_state()
        base = state.get("acknowledged_sha")
        baseline_note = None
        if not base:
            detail = _fetch_json(f"{GITHUB_COMMITS_API}/{head}")
            parents = detail.get("parents") or []
            if not parents:
                raise RuntimeError("最新提交无父提交，无法生成差异报告")
            base = parents[0]["sha"]
            baseline_note = "尚未确认过基线版本，本次仅对比最新一次提交"

        cache_key = f"{base[:12]}...{head[:12]}"
        cached = _load_report_cache()
        if (cached and cached.get("cache_key") == cache_key
                and cached.get("format_version") == REPORT_FORMAT_VERSION):
            return cached

        try:
            comparison = _fetch_json(f"{GITHUB_COMPARE_API}/{base}...{head}")
        except requests.RequestException:
            # 基线提交可能已被 force-push 移除，退回只对比最新一次提交
            detail = _fetch_json(f"{GITHUB_COMMITS_API}/{head}")
            parents = detail.get("parents") or []
            if not parents:
                raise RuntimeError("无法对比上游版本，且最新提交无父提交")
            base = parents[0]["sha"]
            baseline_note = "已确认的基线版本在上游历史中已不存在，仅对比最新一次提交"
            cache_key = f"{base[:12]}...{head[:12]}"
            cached = _load_report_cache()
            if (cached and cached.get("cache_key") == cache_key
                    and cached.get("format_version") == REPORT_FORMAT_VERSION):
                return cached
            comparison = _fetch_json(f"{GITHUB_COMPARE_API}/{base}...{head}")

        if comparison.get("status") == "identical":
            report = {
                "format_version": REPORT_FORMAT_VERSION,
                "cache_key": cache_key,
                "base_sha": base,
                "head_sha": head,
                "baseline_note": None,
                "total_commits": 0,
                "commits": [],
                "files": [],
                "backend_impacts": [],
                "new_upstream_functions": [],
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        else:
            commits = []
            for item in comparison.get("commits") or []:
                commit = item.get("commit", {})
                commits.append({
                    "sha": item.get("sha", ""),
                    "message": (commit.get("message") or "").splitlines()[0],
                    "date": (commit.get("committer") or {}).get("date", ""),
                    "author": (commit.get("author") or {}).get("name", ""),
                    "url": item.get("html_url", COMMITS_PAGE),
                })
            files = comparison.get("files") or []
            changed_funcs, file_summaries = _extract_changed_functions(files)
            index = _backend_function_index()
            impacts: dict = {}
            new_funcs = []
            for func in sorted(changed_funcs):
                target = index.get(func)
                if target:
                    impacts.setdefault(target, []).append(func)
                else:
                    new_funcs.append(func)
            report = {
                "format_version": REPORT_FORMAT_VERSION,
                "cache_key": cache_key,
                "base_sha": base,
                "head_sha": head,
                "baseline_note": baseline_note,
                "total_commits": len(commits),
                "commits": commits,
                "files": file_summaries,
                "backend_impacts": [
                    {"backend_file": f, "functions": funcs}
                    for f, funcs in sorted(impacts.items())
                ],
                "new_upstream_functions": new_funcs,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_CACHE_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
