"""十二章 AI 报告生成编排。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import threading
import time
from typing import Callable, Optional

from app.core.config import settings
from app.services.chapter_md import assemble_report, extract_key_facts, render_chapter_data
from app.services.chapter_prompts import CHAPTER_HINTS, COMMENT_SYSTEM, SUMMARY_SYSTEM
from app.services.chapters import CHAPTERS, COMMENT_CHAPTER_KEYS
from app.services.full_aggregator import build_full_snapshot
from app.services.llm_client import chat


def _usage_total(usages: list[dict]) -> dict:
    keys = {key for usage in usages for key in usage}
    return {key: sum(int(usage.get(key) or 0) for usage in usages) for key in keys}


def _normalize_comment(content: str) -> str:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(line if line.startswith(">") else f"> {line}" for line in lines)


def _chapter_list(states: dict[str, dict]) -> list[dict]:
    return [{"key": item["key"], "title": item["title"], "state": states[item["key"]]["state"]}
            for item in CHAPTERS]


def _notify(on_progress, states, status, current, done):
    if on_progress:
        on_progress({
            "status": status,
            "current_chapter": current,
            "chapters": _chapter_list(states),
            "progress": {"done": done, "total": len(CHAPTERS)},
        })


def generate_report(code: str, on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    started = time.monotonic()
    snapshot = build_full_snapshot(code, on_progress=on_progress)
    states = {
        item["key"]: {
            "key": item["key"], "title": item["title"], "state": "data_ok",
            "data_md": render_chapter_data(item["key"], snapshot), "comment_md": "", "usage": {},
        }
        for item in CHAPTERS
    }
    for key, errors in (snapshot.get("errors") or {}).items():
        if key in states:
            note = "；".join(errors)
            states[key]["data_md"] += f"\n\n> 部分数据源未获取：{note}"
            chapter_data = (snapshot.get("chapters") or {}).get(key) or {}
            if not chapter_data:
                states[key]["state"] = "data_failed"

    lock = threading.Lock()
    done = 0
    usages = []

    def generate_comment(key: str):
        chapter = states[key]
        if chapter["state"] == "data_failed":
            return key, None, {}, None
        with lock:
            chapter["state"] = "generating"
            _notify(on_progress, states, "generating", chapter["title"], done)
        system = COMMENT_SYSTEM.format(stock=f"{snapshot['name']}（{snapshot['code']}）", chapter=chapter["title"])
        user = f"本章要求：{CHAPTER_HINTS[key]}\n\n以下为后端确定性生成的数据：\n\n{chapter['data_md']}"
        try:
            content, usage = chat(
                system, user, temperature=0.3,
                max_tokens=settings.REPORT_CHAPTER_MAX_TOKENS,
            )
            return key, _normalize_comment(content), usage, None
        except Exception as exc:
            return key, None, {}, str(exc)

    with ThreadPoolExecutor(max_workers=settings.REPORT_AI_CONCURRENCY) as pool:
        futures = [pool.submit(generate_comment, key) for key in COMMENT_CHAPTER_KEYS]
        for future in as_completed(futures):
            key, comment, usage, error = future.result()
            with lock:
                if error:
                    states[key]["state"] = "comment_failed"
                    states[key]["comment_md"] = "> AI 点评生成失败，可单独重试。"
                    states[key]["error"] = error
                elif comment is None:
                    states[key]["comment_md"] = "> 本章数据未获取，未调用 AI 点评。"
                else:
                    states[key]["state"] = "ok"
                    states[key]["comment_md"] = comment
                    states[key]["usage"] = usage
                    usages.append(usage)
                done += 1
                _notify(on_progress, states, "generating", states[key]["title"], done)

    summary = states["ch10_summary"]
    summary["state"] = "generating"
    _notify(on_progress, states, "generating", summary["title"], done)
    comments = {key: value["comment_md"] for key, value in states.items()}
    summary_user = (
        "以下是确定性关键事实和前章点评：\n\n"
        f"{extract_key_facts(snapshot, comments)}\n\n"
        "以下 PEG 情景表由后端计算，请只评价：\n\n"
        f"{summary['data_md']}"
    )
    try:
        content, usage = chat(
            SUMMARY_SYSTEM, summary_user, temperature=0.3,
            max_tokens=settings.REPORT_FINAL_MAX_TOKENS,
        )
        summary["comment_md"] = content.strip()
        summary["usage"] = usage
        summary["state"] = "ok"
        usages.append(usage)
    except Exception as exc:
        summary["comment_md"] = "> 综合评估生成失败，可单独重试。"
        summary["state"] = "comment_failed"
        summary["error"] = str(exc)
    done += 1
    _notify(on_progress, states, "assembling", summary["title"], done)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    track = (snapshot.get("chapters") or {}).get("ch2_track") or {}
    quote = ((snapshot.get("chapters") or {}).get("ch1_quote") or {}).get("quote") or {}
    valuation = ((snapshot.get("chapters") or {}).get("ch3_valuation") or {}).get("valuation") or {}
    meta = {
        "code": snapshot["code"], "name": snapshot["name"], "generated_at": generated_at,
        "model": settings.LLM_MODEL, "duration_s": round(time.monotonic() - started, 1),
        "usage": _usage_total(usages), "data_errors": snapshot.get("errors") or {},
        "profile": track.get("profile") or {}, "industry": (track.get("profile") or {}).get("industry"),
        "concept_tags": track.get("concept_tags") or [], "price": quote.get("price"),
        "change_pct": quote.get("change_pct"), "pe_ttm": valuation.get("pe_ttm"),
    }
    full_markdown = assemble_report(snapshot, states, meta)
    return {
        "code": snapshot["code"], "name": snapshot["name"], "meta": meta,
        "chapters": [states[item["key"]] for item in CHAPTERS],
        "snapshot": snapshot, "full_markdown": full_markdown,
    }


def retry_report_chapter(report: dict, key: str,
                         on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    chapters = {chapter["key"]: chapter for chapter in report.get("chapters") or []}
    if key not in chapters:
        raise ValueError(f"报告中不存在章节: {key}")
    chapter = chapters[key]
    if on_progress:
        on_progress({"status": "retrying", "current_chapter": chapter["title"]})
    if key == "ch10_summary":
        comments = {item_key: item.get("comment_md") or "" for item_key, item in chapters.items()}
        user = (f"{extract_key_facts(report['snapshot'], comments)}\n\n"
                f"后端计算的估值情景表：\n{chapter.get('data_md') or ''}")
        content, usage = chat(SUMMARY_SYSTEM, user, temperature=0.3,
                              max_tokens=settings.REPORT_FINAL_MAX_TOKENS)
        chapter["comment_md"] = content.strip()
    else:
        system = COMMENT_SYSTEM.format(
            stock=f"{report['meta']['name']}（{report['meta']['code']}）", chapter=chapter["title"]
        )
        user = f"本章要求：{CHAPTER_HINTS[key]}\n\n{chapter.get('data_md') or ''}"
        content, usage = chat(system, user, temperature=0.3,
                              max_tokens=settings.REPORT_CHAPTER_MAX_TOKENS)
        chapter["comment_md"] = _normalize_comment(content)
    chapter["usage"] = usage
    chapter["state"] = "ok"
    chapter.pop("error", None)
    report["meta"]["usage"] = _usage_total([item.get("usage") or {} for item in chapters.values()])
    report["full_markdown"] = assemble_report(report["snapshot"], chapters, report["meta"])
    return report
