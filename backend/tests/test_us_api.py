from fastapi.testclient import TestClient

from app.core.instrument import parse_us_instrument
from app.main import app
from app.services import us_data_task, us_report_task


def test_invalid_us_symbol_returns_400():
    client = TestClient(app)
    assert client.post("/api/us/data/BAD%2E%2EX/collect", json={"refresh": False}).status_code == 400
    assert client.post("/api/us/report/BAD%2E%2EX/generate", json={"refresh": False, "source": "web"}).status_code == 400


def test_us_status_404_and_data_market(monkeypatch, tmp_path):
    instrument = parse_us_instrument("AAPL")
    monkeypatch.setattr(us_data_task, "TASK_DIR", tmp_path)
    monkeypatch.setattr(us_data_task, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(us_report_task, "TASK_DIR", tmp_path)
    monkeypatch.setattr(us_report_task, "REPORT_DIR", tmp_path)
    client = TestClient(app)
    assert client.get("/api/us/data/AAPL/status").status_code == 404
    assert client.get("/api/us/data/AAPL").status_code == 404

    snapshot = {"market": "US", "code": "AAPL", "name": "Apple", "currency": "USD", "chapters": {}, "errors": {}, "source_errors": {}, "sources": [], "fetched_at": "2026-10-19 00:00:00"}
    payload = {"market": "US", "code": "AAPL", "name": "Apple", "fetched_at": "2026-10-19 00:00:00", "cached": True, "chapters": [], "errors": {}, "source_errors": {}, "snapshot": snapshot}
    path = tmp_path / f"{instrument.canonical_key}.json"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    monkeypatch.setattr(us_data_task, "_task_path", lambda _inst: tmp_path / "status.json")
    monkeypatch.setattr(us_data_task, "_snapshot_path", lambda _inst, day=None: path)
    monkeypatch.setattr(us_data_task, "_lock_path", lambda _inst: tmp_path / "status.lock")
    assert client.get("/api/us/data/AAPL").status_code == 200
    assert client.get("/api/us/data/AAPL").json()["market"] == "US"


def test_report_list_accepts_market_parameter():
    client = TestClient(app)
    assert client.get("/api/report/list?market=US").status_code == 200
    assert client.get("/api/report/list?market=BAD").status_code == 422
