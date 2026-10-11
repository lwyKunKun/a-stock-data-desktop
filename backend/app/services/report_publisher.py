"""报告写入 Obsidian，并同步、推送和部署 stock-review。"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import unicodedata
from datetime import datetime

from app.core.categories import resolve_category
from app.core.config import settings

_publish_lock = threading.Lock()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def _run_command(args: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), text=True, capture_output=True,
                          timeout=timeout, check=False)


def _stage(ok: bool, **kwargs) -> dict:
    return {"ok": ok, **kwargs}


def _safe_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", normalized).replace("..", "-")
    cleaned = cleaned.strip(". ")[:80]
    if not cleaned:
        raise ValueError("股票名称无法生成安全文件名")
    return cleaned


def _report_identity(report: dict) -> tuple[str, str, dict]:
    meta = report.get("meta") or {}
    code = str(meta.get("code") or report.get("code") or "").strip()
    raw_name = str(meta.get("name") or report.get("name") or "")
    if not code or not raw_name.strip():
        raise ValueError("报告缺少 meta.code 或 meta.name")
    return code, _safe_name(raw_name), meta


def _category(report: dict, meta: dict) -> str:
    profile = meta.get("profile") or {}
    if meta.get("industry") and not profile.get("industry"):
        profile = {**profile, "industry": meta["industry"]}
    tags = meta.get("concept_tags") or []
    snapshot = report.get("snapshot") or {}
    track = (snapshot.get("chapters") or {}).get("ch2_track") or {}
    profile = track.get("profile") or profile
    tags = track.get("concept_tags") or track.get("tags") or tags
    return resolve_category(profile, tags)


def _log_summary(report: dict, meta: dict, category: str) -> str:
    summary = str(meta.get("summary") or "").strip()
    if not summary:
        price = meta.get("price")
        change = meta.get("change_pct")
        pe = meta.get("pe_ttm")
        parts = [f"分类：{category}"]
        if price is not None:
            parts.append(f"现价：{price}")
        if change is not None:
            parts.append(f"涨跌：{change}%")
        if pe is not None:
            parts.append(f"PE(TTM)：{pe}")
        summary = "；".join(parts)
    return summary.replace("\n", " ").replace("|", "｜")[:300]


def _update_log(log_path: Path, code: str, name: str, summary: str, now: datetime) -> None:
    header = (
        f"# 操作日志 - {now:%Y年%m月%d日}\n\n"
        "| 时间 | 股票代码 | 股票名称 | 查询类型 | 今日查询次数 | 备注 |\n"
        "|------|---------|---------|---------|------------|------|\n"
    )
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else header
    count = sum(
        1 for line in existing.splitlines()
        if line.startswith("|") and len(line.split("|")) > 2 and line.split("|")[2].strip() == code
    ) + 1
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += f"| {now:%H:%M} | {code} | {name} | 全维度分析 | 第 {count} 次 | {summary} |\n"
    _atomic_write(log_path, existing)


def _dirty_paths(repo: Path) -> set[str]:
    result = _run_command(["git", "status", "--porcelain", "-z"], repo, 30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status 失败")
    paths = set()
    for entry in result.stdout.split("\0"):
        if entry:
            paths.add(entry[3:])
    return paths


def _command_error(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "命令执行失败").strip()[-2000:]


def publish_report(report: dict) -> dict:
    """发布报告。失败以结构化状态返回，不影响应用内报告缓存。"""
    publication = {
        "obsidian": {"enabled": settings.OBSIDIAN_SYNC_ENABLED, "ok": False},
        "stock_review": {"enabled": settings.STOCK_REVIEW_PUBLISH_ENABLED, "ok": False},
        "git": {"enabled": settings.STOCK_REVIEW_PUBLISH_ENABLED, "ok": False},
        "deploy": {"enabled": settings.STOCK_REVIEW_PUBLISH_ENABLED, "ok": False},
    }
    try:
        code, name, meta = _report_identity(report)
        markdown = report.get("full_markdown") or ""
        if not markdown:
            raise ValueError("报告缺少 full_markdown")
        category = _category(report, meta)
        now = datetime.now()

        if not settings.OBSIDIAN_SYNC_ENABLED:
            publication["obsidian"] = _stage(True, enabled=False, skipped=True)
            publication["stock_review"] = _stage(True, enabled=False, skipped=True)
            publication["git"] = _stage(True, enabled=False, skipped=True)
            publication["deploy"] = _stage(True, enabled=False, skipped=True)
            publication["ok"] = True
            return publication

        vault = Path(settings.OBSIDIAN_VAULT_PATH)
        stock_root = vault / "01-Projects" / "股票基本面"
        report_path = stock_root / category / f"{name}-{code}.md"
        log_path = stock_root / "log" / f"{now:%Y}" / f"{now:%m}" / f"{now:%Y-%m-%d}.md"
        _atomic_write(report_path, markdown)
        _update_log(log_path, code, name, _log_summary(report, meta, category), now)
        publication["obsidian"] = _stage(
            True, enabled=True, category=category, path=str(report_path), log_path=str(log_path)
        )

        if not settings.STOCK_REVIEW_PUBLISH_ENABLED:
            publication["stock_review"] = _stage(True, enabled=False, skipped=True)
            publication["git"] = _stage(True, enabled=False, skipped=True)
            publication["deploy"] = _stage(True, enabled=False, skipped=True)
            publication["ok"] = True
            return publication

        with _publish_lock:
            repo = Path(settings.STOCK_REVIEW_PATH)
            output_root = repo / "output" / "01-Projects" / "股票基本面"
            output_report = output_root / category / report_path.name
            output_log = output_root / "log" / f"{now:%Y}" / f"{now:%m}" / log_path.name
            output_report.parent.mkdir(parents=True, exist_ok=True)
            output_log.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report_path, output_report)
            shutil.copy2(log_path, output_log)
            publication["stock_review"] = _stage(
                True, enabled=True, paths=[str(output_report), str(output_log)]
            )

            relative = [str(output_report.relative_to(repo)), str(output_log.relative_to(repo))]
            dirty = _dirty_paths(repo)
            unrelated = sorted(dirty - set(relative))
            if unrelated:
                raise RuntimeError(f"stock-review 存在无关未提交改动，已停止自动发布: {unrelated[:10]}")

            add = _run_command(["git", "add", "--", *relative], repo, 30)
            if add.returncode != 0:
                raise RuntimeError(f"git add 失败: {_command_error(add)}")
            changed = _run_command(["git", "diff", "--cached", "--quiet", "--", *relative], repo, 30)
            if changed.returncode == 0:
                publication["git"] = _stage(True, enabled=True, skipped=True, note="内容无变化")
                publication["deploy"] = _stage(True, enabled=True, skipped=True, note="无新提交，无需部署")
                publication["ok"] = True
                return publication
            if changed.returncode != 1:
                raise RuntimeError(f"git diff 失败: {_command_error(changed)}")

            commit = _run_command(
                ["git", "commit", "-m", f"更新：{name}（{code}）全维度分析", "--", *relative], repo, 120
            )
            if commit.returncode != 0:
                raise RuntimeError(f"git commit 失败: {_command_error(commit)}")
            push = _run_command(["git", "push", "origin", "main"], repo, 180)
            push_mode = "origin"
            if push.returncode != 0:
                push = _run_command(
                    ["git", "push", "git@github.com:lwyKunKun/DailyStockReviewAutoScript.git", "main"],
                    repo, 180,
                )
                push_mode = "ssh_fallback"
            if push.returncode != 0:
                raise RuntimeError(f"git push 失败: {_command_error(push)}")
            publication["git"] = _stage(True, enabled=True, push=push_mode,
                                         commit=commit.stdout.strip()[-500:])

            remaining = _dirty_paths(repo)
            if remaining:
                raise RuntimeError(f"推送后工作树仍有改动，已停止 deploy.sh: {sorted(remaining)[:10]}")
            deploy = _run_command(["bash", settings.STOCK_REVIEW_DEPLOY_SCRIPT], repo, 600)
            if deploy.returncode != 0:
                raise RuntimeError(f"部署失败: {_command_error(deploy)}")
            publication["deploy"] = _stage(True, enabled=True, output=deploy.stdout.strip()[-2000:])

        publication["ok"] = True
        return publication
    except Exception as exc:
        publication["ok"] = False
        publication["error"] = str(exc)
        return publication
