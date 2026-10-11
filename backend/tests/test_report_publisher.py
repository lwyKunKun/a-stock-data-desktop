import subprocess
from pathlib import Path

from app.core.categories import resolve_category
from app.core.config import settings
from app.services import report_publisher


def _report():
    return {
        "meta": {
            "code": "600519", "name": "贵州茅台", "industry": "白酒",
            "concept_tags": ["沪股通"], "price": 1500, "change_pct": 1.2, "pe_ttm": 25,
        },
        "full_markdown": "# 贵州茅台-600519 全维度分析\n\n正文\n",
    }


def test_category_specific_rule_precedes_industry():
    assert resolve_category({"industry": "电子"}, ["CPO", "光模块"]) == "光通信"
    assert resolve_category({"industry": "工业金属"}, []) == "工业金属"
    assert resolve_category({}, []) == "未分类"


def test_obsidian_log_appends_and_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setattr(settings, "OBSIDIAN_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "STOCK_REVIEW_PUBLISH_ENABLED", False)

    first = report_publisher.publish_report(_report())
    second = report_publisher.publish_report(_report())

    assert first["ok"] is True and second["ok"] is True
    report_path = Path(second["obsidian"]["path"])
    log_path = Path(second["obsidian"]["log_path"])
    assert report_path.read_text(encoding="utf-8").startswith("# 贵州茅台")
    text = log_path.read_text(encoding="utf-8")
    assert "第 1 次" in text
    assert "第 2 次" in text


def test_stock_review_stages_only_generated_files(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    repo = tmp_path / "stock-review"
    repo.mkdir()
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.setattr(settings, "OBSIDIAN_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "STOCK_REVIEW_PUBLISH_ENABLED", True)
    monkeypatch.setattr(settings, "STOCK_REVIEW_PATH", str(repo))
    monkeypatch.setattr(settings, "STOCK_REVIEW_DEPLOY_SCRIPT", str(repo / "deploy.sh"))

    calls = []

    def fake_run(args, cwd, timeout=180):
        calls.append(args)
        if args[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:4] == ["git", "diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(report_publisher, "_run_command", fake_run)
    result = report_publisher.publish_report(_report())

    assert result["ok"] is True
    add = next(args for args in calls if args[:2] == ["git", "add"])
    staged = add[3:]
    assert len(staged) == 2
    assert all(path.startswith("output/01-Projects/股票基本面/") for path in staged)
    assert ["git", "push", "origin", "main"] in calls
    assert ["bash", str(repo / "deploy.sh")] in calls
