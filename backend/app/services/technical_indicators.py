import math


def _valid_bars(bars: list[dict]) -> list[dict]:
    result = []
    for bar in sorted(bars or [], key=lambda item: str(item.get("date") or "")):
        try:
            close = float(bar["close"])
            high = float(bar["high"])
            low = float(bar["low"])
        except (KeyError, TypeError, ValueError):
            continue
        result.append({**bar, "close": close, "high": high, "low": low})
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def calculate_technical_indicators(bars: list[dict]) -> dict:
    clean = _valid_bars(bars)
    if not clean:
        return {"sample_count": 0, "latest": {}, "series": []}
    closes = [item["close"] for item in clean]
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    k_value = d_value = 50.0
    series = []
    changes = [0.0] + [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(value, 0.0) for value in changes]
    losses = [max(-value, 0.0) for value in changes]

    for index, item in enumerate(clean):
        row = {"date": item.get("date"), "close": item["close"]}
        for period in (5, 10, 20, 50, 200):
            row[f"ma{period}"] = round(sum(closes[index - period + 1:index + 1]) / period, 4) if index >= period - 1 else None
        row.update({
            "ema12": round(ema12[index], 4), "ema26": round(ema26[index], 4),
            "macd_dif": round(dif[index], 4), "macd_dea": round(dea[index], 4),
            "macd_hist": round((dif[index] - dea[index]) * 2, 4),
        })
        for period in (6, 14):
            if index < period:
                row[f"rsi{period}"] = None
            else:
                avg_gain = sum(gains[index - period + 1:index + 1]) / period
                avg_loss = sum(losses[index - period + 1:index + 1]) / period
                row[f"rsi{period}"] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
        if index >= 8:
            window = clean[index - 8:index + 1]
            high, low = max(x["high"] for x in window), min(x["low"] for x in window)
            rsv = (item["close"] - low) / (high - low) * 100 if high != low else 50.0
            k_value = rsv / 3 + k_value * 2 / 3
            d_value = k_value / 3 + d_value * 2 / 3
            row.update({"k": round(k_value, 2), "d": round(d_value, 2), "j": round(3 * k_value - 2 * d_value, 2)})
        else:
            row.update({"k": None, "d": None, "j": None})
        if index >= 19:
            window = closes[index - 19:index + 1]
            mean = sum(window) / 20
            std = math.sqrt(sum((value - mean) ** 2 for value in window) / 20)
            row.update({"boll_upper": round(mean + 2 * std, 4), "boll_middle": round(mean, 4), "boll_lower": round(mean - 2 * std, 4)})
        else:
            row.update({"boll_upper": None, "boll_middle": None, "boll_lower": None})
        series.append(row)

    latest = dict(series[-1])
    highs = [item["high"] for item in clean[-252:]]
    lows = [item["low"] for item in clean[-252:]]
    volumes = [float(item.get("volume") or 0) for item in clean[-20:]]
    returns = [(closes[i] / closes[i - 1] - 1) for i in range(max(1, len(closes) - 20), len(closes)) if closes[i - 1]]
    latest.update({
        "high_52w": max(highs), "low_52w": min(lows),
        "volume_avg_20d": round(sum(volumes) / len(volumes), 2) if volumes else None,
        "volatility_20d_pct": round(math.sqrt(sum((r - sum(returns) / len(returns)) ** 2 for r in returns) / len(returns)) * math.sqrt(252) * 100, 2) if returns else None,
    })
    return {"sample_count": len(clean), "latest": latest, "series": series[-60:]}
