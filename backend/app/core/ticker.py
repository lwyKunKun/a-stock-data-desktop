"""股票代码归一化与市场前缀路由。

从 a-stock-data SKILL.md 移植，是所有数据源调用的前置基础：
- norm_ticker()：任意受支持写法 → 纯 6 位数字
- get_prefix()：6 位码 → 市场前缀 sh/sz/bj
- em_secid() / em_market_code()：东财 push2 接口专用
"""
import re

# 沪市指数白名单：与深市 000xxx 个股同段，需白名单区分
SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}

# 整串锚定匹配，只认受支持写法；市场标识前缀、后缀二选一，不能同时出现。
_TICKER_RE = re.compile(
    r"^(?:(sh|sz|bj)(\d{6})|(\d{6})(?:\.(sh|sz|bj))?)$", re.IGNORECASE)


def _natural_market(digits: str) -> str:
    """6 位码的自然归属市场。仅用于校验显式前缀是否自相矛盾。

    注意 000xxx 是沪指数/深个股共用的歧义段，由调用处单独处理，不走这里。
    """
    if digits.startswith(("4", "8", "92")):
        return "bj"  # 北交所：92x 现行 / 4x·8x 老号段
    if digits[0] in ("5", "6", "9"):
        return "sh"  # 5x 沪 ETF/LOF，6xx 沪个股，9xx 沪 B 股
    return "sz"  # 00x/30x/15x/16x/39x 等


def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀（sh/sz/bj）。支持显式前缀/后缀透传以解决歧义。"""
    c = code.lower().strip()
    if c.endswith((".sh", ".sz", ".bj")):
        return c[-2:]
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):  # 北交所新号段，必须先于下面的 9x 判断
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if c in SH_INDEX:
        return "sh"
    return "sz"


def norm_ticker(code: str, stock_only: bool = False) -> str:
    """任意受支持写法 → 纯 6 位数字代码。

    支持 600519 / SH600519 / sh600519 / 600519.SH / BJ920982 等。
    stock_only=True：个股专用接口传这个，会拒绝显式指数写法。
    ⚠️ 不匹配时抛 ValueError，绝不静默返回空串或猜一个代码。
    """
    raw = str(code).strip()
    m = _TICKER_RE.match(raw)
    if not m:
        raise ValueError(
            f"无法把 {code!r} 解析为 6 位股票代码；"
            f"支持格式：600519 / SH600519 / sh600519 / 600519.SH"
            f"（前缀与后缀二选一，不能同时写）"
        )
    digits = m.group(2) or m.group(3)
    market = (m.group(1) or m.group(4) or "").lower()
    if market:
        if digits.startswith("000"):
            # 000xxx 是沪市指数/深市个股共用的歧义段，显式标识在此是「消歧」不是「矛盾」
            if market == "bj":
                raise ValueError(f"{code!r} 市场标识与号段矛盾：000xxx 不属北交所。")
            if stock_only and market == "sh":
                raise ValueError(
                    f"{code!r} 指向沪市指数而非个股（沪市无 000xxx 个股），本接口只服务个股。"
                    f"要查同号段的深市个股请显式传 sz{digits}。"
                )
        else:
            nat = _natural_market(digits)
            if market != nat:
                raise ValueError(
                    f"{code!r} 的市场标识与号段矛盾：{digits} 属 {nat} 市，而不是 {market} 市。"
                    f"（改用 {nat}{digits} 或去掉市场标识）"
                )
    return digits


def em_market_code(code: str) -> int:
    """东财 secid 的市场号：沪=1，深/北=0。

    ⚠️ 绝不要用 code.startswith("6") 判市场——会把沪市 ETF(51x)、
    科创板 ETF(588x)、沪 B(900x) 全部错判成深市。
    """
    return 1 if get_prefix(code) == "sh" else 0


def em_secid(code: str) -> str:
    """东财 push2/push2his 的 secid，如 1.600519 / 0.300750。"""
    return f"{em_market_code(code)}.{norm_ticker(code)}"
