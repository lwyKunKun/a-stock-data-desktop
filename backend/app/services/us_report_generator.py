from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
from typing import Callable, Optional

from app.core.config import settings
from app.core.instrument import Instrument
from app.services.llm_client import chat
from app.services.report_generator import _data_warnings, _normalize_comment, _strip_echoed_heading, _usage_total
from app.services.us_aggregator import build_us_snapshot
from app.services.us_chapter_md import assemble_us_report, extract_us_key_facts, render_us_chapter_data
from app.services.us_chapter_prompts import US_CHAPTER_HINTS, US_COMMENT_SYSTEM, US_SUMMARY_SYSTEM
from app.services.us_chapters import US_CHAPTERS, US_COMMENT_CHAPTER_KEYS


def _notify(callback, states, status, current, done):
    if callback:
        callback({"status": status, "current_chapter": current,
                  "chapters": [{"key": item["key"], "title": item["title"], "state": states[item["key"]]["state"]} for item in US_CHAPTERS],
                  "progress": {"done": done, "total": len(US_CHAPTERS)}})


def generate_us_report(instrument: Instrument, on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    started = time.monotonic()
    snapshot = build_us_snapshot(instrument, on_progress=on_progress, sec_contact=settings.SEC_CONTACT)
    states = {item["key"]: {"key": item["key"], "title": item["title"], "state": "data_ok",
              "data_md": render_us_chapter_data(item["key"], snapshot), "comment_md": "", "usage": {}}
              for item in US_CHAPTERS}
    for key, errors in (snapshot.get("errors") or {}).items():
        warnings = _data_warnings(errors)
        if key in states and warnings:
            states[key]["data_warnings"] = warnings
            states[key]["data_md"] += f"\n\n> 部分数据源不可用（{len(warnings)}项），其余数据不受影响。"
    usages, done = [], 0

    def generate(key: str):
        chapter = states[key]
        chapter["state"] = "generating"
        system = US_COMMENT_SYSTEM.format(stock=f"{snapshot['name']}（{snapshot['code']}）", chapter=chapter["title"])
        user = f"本章要求：{US_CHAPTER_HINTS[key]}\n\n{chapter['data_md']}"
        try:
            content, usage = chat(system, user, max_tokens=settings.REPORT_CHAPTER_MAX_TOKENS)
            return key, _normalize_comment(content), usage, None
        except Exception as exc:
            return key, None, {}, str(exc)

    with ThreadPoolExecutor(max_workers=settings.REPORT_AI_CONCURRENCY) as pool:
        futures = [pool.submit(generate, key) for key in US_COMMENT_CHAPTER_KEYS]
        for future in as_completed(futures):
            key, content, usage, error = future.result()
            if error:
                states[key].update({"state": "comment_failed", "comment_md": "> AI点评生成失败，可单独重试。", "error": error})
            else:
                states[key].update({"state": "ok", "comment_md": content, "usage": usage})
                usages.append(usage)
            done += 1
            _notify(on_progress, states, "generating", states[key]["title"], done)

    summary = states["us_ch10_summary"]
    summary["state"] = "generating"
    comments = {key: value.get("comment_md") or "" for key, value in states.items()}
    try:
        content, usage = chat(US_SUMMARY_SYSTEM, extract_us_key_facts(snapshot, comments), max_tokens=settings.REPORT_FINAL_MAX_TOKENS)
        summary.update({"state": "ok", "comment_md": _strip_echoed_heading(content, summary["title"]), "usage": usage})
        usages.append(usage)
    except Exception as exc:
        summary.update({"state": "comment_failed", "comment_md": "> 综合评估生成失败，可单独重试。", "error": str(exc)})
    _notify(on_progress, states, "assembling", summary["title"], len(US_CHAPTERS))
    quote = ((snapshot.get("chapters") or {}).get("us_ch1_quote") or {}).get("quote") or {}
    profile = ((snapshot.get("chapters") or {}).get("us_ch4_profile") or {}).get("profile") or {}
    valuation = ((snapshot.get("chapters") or {}).get("us_ch5_valuation") or {}).get("valuation") or {}
    meta = {"market": "US", "code": snapshot["code"], "name": snapshot["name"], "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": settings.LLM_MODEL, "duration_s": round(time.monotonic() - started, 1), "usage": _usage_total(usages),
            "industry": profile.get("industry") or profile.get("sector") or "", "price": quote.get("price"),
            "change_pct": quote.get("change_pct"), "pe_ttm": valuation.get("pe_ttm") or quote.get("pe_ttm")}
    chapters = [states[item["key"]] for item in US_CHAPTERS]
    return {"market": "US", "code": snapshot["code"], "name": snapshot["name"], "meta": meta,
            "chapters": chapters, "snapshot": snapshot, "full_markdown": assemble_us_report(snapshot, chapters, meta)}


def retry_us_report_chapter(report: dict, key: str, on_progress=None) -> dict:
    chapters = {item["key"]: item for item in report.get("chapters") or []}
    if key not in chapters:
        raise ValueError(f"报告中不存在章节: {key}")
    chapter = chapters[key]
    if key == "us_ch10_summary":
        comments = {item_key: item.get("comment_md") or "" for item_key, item in chapters.items()}
        content, usage = chat(US_SUMMARY_SYSTEM, extract_us_key_facts(report["snapshot"], comments), max_tokens=settings.REPORT_FINAL_MAX_TOKENS)
        chapter["comment_md"] = _strip_echoed_heading(content, chapter["title"])
    else:
        system = US_COMMENT_SYSTEM.format(stock=f"{report['name']}（{report['code']}）", chapter=chapter["title"])
        content, usage = chat(system, f"本章要求：{US_CHAPTER_HINTS[key]}\n\n{chapter.get('data_md') or ''}", max_tokens=settings.REPORT_CHAPTER_MAX_TOKENS)
        chapter["comment_md"] = _normalize_comment(content)
    chapter.update({"state": "ok", "usage": usage})
    chapter.pop("error", None)
    ordered = [chapters[item["key"]] for item in US_CHAPTERS]
    report["full_markdown"] = assemble_us_report(report["snapshot"], ordered, report["meta"])
    report["chapters"] = ordered
    return report
