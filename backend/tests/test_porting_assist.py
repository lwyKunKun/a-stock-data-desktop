"""porting_assist 单元测试 —— 全程 mock LLM 与 GitHub 请求，不触网、不消耗 token。"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app.services import porting_assist

FAKE_CACHE_KEY = "aaaa1111bbbb...cccc2222dddd"
FAKE_REPORT = {
    "cache_key": FAKE_CACHE_KEY,
    "base_sha": "a" * 40,
    "head_sha": "b" * 40,
    "baseline_note": None,
    "total_commits": 1,
    "commits": [{
        "sha": "b" * 40,
        "message": "fix: 示例修复",
        "date": "2026-10-11T00:00:00Z",
        "author": "测试",
        "url": "https://example.com",
    }],
    "files": [],
    "backend_impacts": [{"backend_file": "app/datasources/valuation.py", "functions": ["pe_digestion"]}],
    "new_upstream_functions": [],
    "generated_at": "2026-10-12 17:00:00",
}

VALID_CONTENT = '"""估值模块。"""\nimport math\n\n\ndef pe_digestion():\n    return None\n'
ALLOWED = {"app/datasources/valuation.py"}


def _llm_json(files):
    return json.dumps({"files": files, "skipped": []}, ensure_ascii=False)


# ── _parse_suggestions ──

def test_parse_valid_suggestion():
    raw = _llm_json([{
        "backend_file": "app/datasources/valuation.py",
        "functions": ["pe_digestion"],
        "explanation": "负增长返回 None",
        "confidence": "high",
        "full_content": VALID_CONTENT,
    }])
    parsed = porting_assist._parse_suggestions(raw, ALLOWED, {})
    assert len(parsed["files"]) == 1
    assert parsed["files"][0]["confidence"] == "high"
    assert parsed["skipped"] == []


def test_parse_strips_markdown_fence():
    raw = "```json\n" + _llm_json([{
        "backend_file": "app/datasources/valuation.py",
        "full_content": VALID_CONTENT,
    }]) + "\n```"
    parsed = porting_assist._parse_suggestions(raw, ALLOWED, {})
    assert len(parsed["files"]) == 1


def test_parse_out_of_scope_file_goes_to_skipped():
    raw = _llm_json([
        {
            "backend_file": "app/datasources/valuation.py",
            "full_content": VALID_CONTENT,
        },
        {
            "backend_file": "app/core/ticker.py",
            "full_content": "x = 1\n",
        },
    ])
    parsed = porting_assist._parse_suggestions(raw, ALLOWED, {})
    assert len(parsed["files"]) == 1
    assert parsed["skipped"][0]["backend_file"] == "app/core/ticker.py"


def test_parse_syntax_error_goes_to_skipped():
    raw = _llm_json([
        {
            "backend_file": "app/datasources/valuation.py",
            "full_content": VALID_CONTENT,
        },
        {
            "backend_file": "app/datasources/valuation.py",
            "full_content": "def broken(:\n",
        },
    ])
    parsed = porting_assist._parse_suggestions(raw, ALLOWED, {})
    assert len(parsed["files"]) == 1
    assert "语法错误" in parsed["skipped"][0]["reason"]


def test_parse_non_json_raises():
    with pytest.raises(RuntimeError):
        porting_assist._parse_suggestions("抱歉，我无法完成这个任务", ALLOWED, {})


@pytest.mark.parametrize("payload", [
    {"files": {"bad": "shape"}, "skipped": []},
    {"files": "not-a-list", "skipped": []},
    {"files": 1, "skipped": []},
    {"files": [], "skipped": {"bad": "shape"}},
    ["top-level-list"],
    [{"files": [{
        "backend_file": "app/datasources/valuation.py",
        "full_content": VALID_CONTENT,
    }], "skipped": []}],
])
def test_parse_malformed_container_raises_runtime_error(payload):
    with pytest.raises(RuntimeError):
        porting_assist._parse_suggestions(json.dumps(payload), ALLOWED, {})


def test_parse_rejects_prose_wrapped_json_without_fence():
    raw = "这是建议：" + _llm_json([{
        "backend_file": "app/datasources/valuation.py",
        "full_content": VALID_CONTENT,
    }])
    with pytest.raises(RuntimeError):
        porting_assist._parse_suggestions(raw, ALLOWED, {})


def test_parse_invalid_items_are_skipped_without_attribute_error():
    raw = json.dumps({
        "files": [
            None,
            "bad-item",
            {"backend_file": "app/datasources/valuation.py", "full_content": VALID_CONTENT},
        ],
        "skipped": [None, "bad-skip"],
    })
    parsed = porting_assist._parse_suggestions(raw, ALLOWED, {})
    assert len(parsed["files"]) == 1
    assert len(parsed["skipped"]) == 4
    assert all(isinstance(item["reason"], str) for item in parsed["skipped"])


def test_parse_all_invalid_raises():
    raw = json.dumps({"files": [{"backend_file": "app/core/ticker.py", "full_content": "x = 1\n"}]})
    with pytest.raises(RuntimeError):
        porting_assist._parse_suggestions(raw, ALLOWED, {})


# ── generate ──

@pytest.fixture()
def patched_generate(monkeypatch, tmp_path):
    """mock LLM/GitHub/报告缓存，建议目录指向 tmp，返回 (chat_calls, 写好的建议路径)。"""
    chat_calls = []

    def fake_chat(system, user, max_tokens=800, timeout=None, retries=None):
        chat_calls.append({"max_tokens": max_tokens})
        return _llm_json([{
            "backend_file": "app/datasources/valuation.py",
            "functions": ["pe_digestion"],
            "explanation": "示例",
            "confidence": "high",
            "full_content": VALID_CONTENT,
        }]), {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    monkeypatch.setattr(porting_assist, "chat", fake_chat)
    monkeypatch.setattr(porting_assist, "SUGGEST_DIR", tmp_path / "suggestions")
    monkeypatch.setattr(porting_assist, "settings",
                        SimpleNamespace(llm_ready=True, LLM_MODEL="mock-model"))
    monkeypatch.setattr(porting_assist.datasource_watch, "_load_report_cache",
                        lambda: FAKE_REPORT)
    monkeypatch.setattr(porting_assist, "_fetch_full_patches", lambda base, head: {"SKILL.md": "diff"})
    monkeypatch.setattr(porting_assist, "_read_backend_sources", lambda impacts: {
        "app/datasources/valuation.py": {
            "content": "old\n",
            "sha256": hashlib.sha256(b"old\n").hexdigest(),
        },
    })
    return chat_calls


def test_generate_calls_llm_and_caches(monkeypatch, patched_generate):
    first = porting_assist.generate(FAKE_CACHE_KEY)
    assert first["files"][0]["full_content"] == VALID_CONTENT
    assert first["usage"]["total_tokens"] == 150
    assert len(patched_generate) == 1

    # 第二次直接命中磁盘缓存，不再调 LLM
    second = porting_assist.generate(FAKE_CACHE_KEY)
    assert len(patched_generate) == 1
    assert second["files"][0]["backend_file"] == first["files"][0]["backend_file"]


def test_generate_refresh_bypasses_cache(monkeypatch, patched_generate):
    porting_assist.generate(FAKE_CACHE_KEY)
    porting_assist.generate(FAKE_CACHE_KEY, refresh=True)
    assert len(patched_generate) == 2


def test_generate_rejects_stale_cache_key(monkeypatch, patched_generate):
    with pytest.raises(RuntimeError):
        porting_assist.generate("zzzz9999yyyy...xxxx8888wwww")


# ── apply ──

@pytest.fixture()
def apply_env(monkeypatch, tmp_path):
    """在 tmp 目录搭一套假 backend/app，写入建议缓存与报告缓存。"""
    backend_dir = tmp_path / "backend"
    target_dir = backend_dir / "app" / "datasources"
    target_dir.mkdir(parents=True)
    target = target_dir / "valuation.py"
    target.write_text("old\n", encoding="utf-8")

    suggestion = {
        "cache_key": FAKE_CACHE_KEY,
        "files": [{
            "backend_file": "app/datasources/valuation.py",
            "functions": ["pe_digestion"],
            "explanation": "示例",
            "confidence": "high",
            "full_content": VALID_CONTENT,
            "source_sha256": hashlib.sha256(b"old\n").hexdigest(),
        }],
        "skipped": [],
    }
    suggest_dir = tmp_path / "suggestions"
    suggest_dir.mkdir()
    (suggest_dir / f"{FAKE_CACHE_KEY}.json").write_text(
        json.dumps(suggestion, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(porting_assist, "BACKEND_DIR", backend_dir)
    monkeypatch.setattr(porting_assist, "APP_ROOT", backend_dir / "app")
    monkeypatch.setattr(porting_assist, "SUGGEST_DIR", suggest_dir)
    monkeypatch.setattr(porting_assist, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(porting_assist.datasource_watch, "_load_report_cache",
                        lambda: FAKE_REPORT)
    return target


def test_apply_writes_file_with_backup(apply_env):
    result = porting_assist.apply(FAKE_CACHE_KEY, ["app/datasources/valuation.py"])
    assert result["applied"] == ["app/datasources/valuation.py"]
    assert result["rejected"] == []
    assert apply_env.read_text(encoding="utf-8") == VALID_CONTENT
    backup = Path(result["backups"][0]["backup_path"])
    assert backup.read_text(encoding="utf-8") == "old\n"
    assert "重启" in result["restart_hint"]
    compile(apply_env.read_text(encoding="utf-8"), "valuation.py", "exec")


def test_apply_rejects_modified_source(apply_env):
    apply_env.write_text("changed by someone\n", encoding="utf-8")
    result = porting_assist.apply(FAKE_CACHE_KEY, ["app/datasources/valuation.py"])
    assert result["applied"] == []
    assert "被修改" in result["rejected"][0]["reason"]


def test_apply_rejects_out_of_scope(apply_env):
    result = porting_assist.apply(FAKE_CACHE_KEY, ["app/core/ticker.py"])
    assert result["applied"] == []
    assert result["rejected"][0]["reason"] == "不在建议列表中"


def test_apply_rejects_path_traversal():
    with pytest.raises(RuntimeError):
        porting_assist._resolve_backend_file("../outside.py")
    with pytest.raises(RuntimeError):
        porting_assist._resolve_backend_file("app/../outside.py")


def test_apply_missing_suggestion():
    with pytest.raises(RuntimeError):
        porting_assist.apply("nonexistent-key-000", ["app/datasources/valuation.py"])


def test_invalid_cache_key_rejected():
    with pytest.raises(RuntimeError):
        porting_assist.generate("../../etc/passwd")
    with pytest.raises(RuntimeError):
        porting_assist.load("bad key with spaces")


def test_datasource_function_index_includes_valuation_service():
    index = porting_assist.datasource_watch._backend_function_index()
    assert index["pe_digestion"] == "app/services/valuation.py"
    assert index["full_valuation"] == "app/services/valuation.py"


def test_report_fallback_rejects_old_format_cache(monkeypatch, tmp_path):
    """基线被 force-push 移除时，fallback 分支也必须拒绝旧格式缓存。"""
    watch = porting_assist.datasource_watch
    old_base, fallback_base, head = "a" * 40, "c" * 40, "b" * 40
    fallback_key = f"{fallback_base[:12]}...{head[:12]}"
    stale = {
        "cache_key": fallback_key,
        "format_version": watch.REPORT_FORMAT_VERSION - 1,
        "backend_impacts": [],
        "sentinel": "stale",
    }
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url == f"{watch.GITHUB_COMPARE_API}/{old_base}...{head}":
            raise requests.RequestException("旧基线不存在")
        if url == f"{watch.GITHUB_COMMITS_API}/{head}":
            return {"parents": [{"sha": fallback_base}]}
        if url == f"{watch.GITHUB_COMPARE_API}/{fallback_base}...{head}":
            return {"status": "identical"}
        raise AssertionError(f"意外 URL：{url}")

    monkeypatch.setattr(watch, "_ensure_fresh", lambda: None)
    monkeypatch.setattr(watch, "_last_latest", {"sha": head})
    monkeypatch.setattr(watch, "_load_state", lambda: {"acknowledged_sha": old_base})
    monkeypatch.setattr(watch, "_load_report_cache", lambda: stale)
    monkeypatch.setattr(watch, "_fetch_json", fake_fetch)
    monkeypatch.setattr(watch, "REPORT_CACHE_PATH", tmp_path / "report.json")

    result = watch.build_update_report()
    assert result["format_version"] == watch.REPORT_FORMAT_VERSION
    assert "sentinel" not in result
    assert f"{watch.GITHUB_COMPARE_API}/{fallback_base}...{head}" in calls
