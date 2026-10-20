from app.core.instrument import Instrument, parse_us_instrument, parse_yahoo_symbol
from app.core import ticker


def test_parse_us_instrument_normalizes():
    assert parse_us_instrument("aapl").symbol == "AAPL"
    assert parse_us_instrument("BRK.B").canonical_key == "us__BRK.B"
    assert parse_us_instrument("BRK-B").yahoo_symbol == "BRK-B"


def test_parse_us_instrument_rejects_invalid():
    for raw in ("", "../AAPL", "A..B", "a" * 20, "NASDAQ:AAPL"):
        try:
            parse_us_instrument(raw)
        except ValueError:
            continue
        raise AssertionError(f"should reject: {raw}")


def test_parse_yahoo_symbol_allows_global_suffix():
    instrument = parse_yahoo_symbol("0700.HK")
    assert instrument.market == "GLOBAL"
    assert instrument.canonical_key == "global__0700.HK"


def test_cn_ticker_boundary_unchanged():
    assert ticker.norm_ticker("600519") == "600519"
    try:
        ticker.norm_ticker("AAPL")
    except ValueError:
        return
    raise AssertionError("A 股校验不应接受 AAPL")
