from dataclasses import dataclass
import re
from typing import Literal

_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,13}(?:[.-][A-Z0-9]{1,4})?$")
_YAHOO_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,19}$")


@dataclass(frozen=True)
class Instrument:
    market: Literal["US", "GLOBAL"]
    symbol: str
    exchange: str | None = None
    asset_type: str = "stock"
    yahoo_symbol: str | None = None

    @property
    def canonical_key(self) -> str:
        prefix = "us" if self.market == "US" else "global"
        return f"{prefix}__{self.symbol}"

    @property
    def display_symbol(self) -> str:
        return self.symbol


def parse_us_instrument(raw: str) -> Instrument:
    symbol = str(raw or "").strip().upper()
    if ".." in symbol or not _US_SYMBOL_RE.fullmatch(symbol):
        raise ValueError("美股代码格式无效，请输入 AAPL、BRK.B 等代码")
    return Instrument(market="US", symbol=symbol, yahoo_symbol=symbol.replace(".", "-"))


def parse_yahoo_symbol(raw: str) -> Instrument:
    symbol = str(raw or "").strip().upper()
    if ".." in symbol or not _YAHOO_SYMBOL_RE.fullmatch(symbol):
        raise ValueError("全球市场代码格式无效")
    return Instrument(market="GLOBAL", symbol=symbol, yahoo_symbol=symbol)


def canonical_instrument_key(instrument: Instrument) -> str:
    return instrument.canonical_key
