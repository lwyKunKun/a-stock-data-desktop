from app.services.technical_indicators import calculate_technical_indicators


def _bars(count=30):
    closes = [100 + i for i in range(count)]
    return [{"date": f"2026-09-{i + 1:02d}", "open": closes[i] - 0.2, "high": closes[i] + 1,
             "low": closes[i] - 1, "close": closes[i], "volume": 1000 + i * 5} for i in range(count)]


def test_empty_input():
    assert calculate_technical_indicators([])["sample_count"] == 0


def test_latest_has_indicators():
    result = calculate_technical_indicators(_bars())
    latest = result["latest"]
    assert latest["ma5"] > 0
    assert latest["rsi14"] is not None
    assert latest["macd_hist"] is not None
    assert latest["boll_upper"] > latest["boll_lower"]
    assert latest["high_52w"] > latest["low_52w"]


def test_series_handles_insufficient_samples():
    result = calculate_technical_indicators(_bars(3))
    assert result["latest"]["ma20"] is None
    assert result["latest"]["rsi14"] is None
