"""东财统一请求入口 —— 限流防封 + 会话复用。

东财系 HTTP 接口（push2 / datacenter / reportapi / search / np-weblist）有风控：
每秒 >5 次 / 单 IP 并发 ≥10 / 1 分钟 ≥200 次 → 临时封 IP（实测住宅 IP 可被封 20+ 小时）。

所有 eastmoney.com 请求一律走 em_get()：
- 串行限流（最小间隔 1s + 随机抖动）
- 复用 Keep-Alive 会话
- 瞬态连接错误 / 429 / 5xx 指数退避重试（403 不重试，那是风控信号）
"""
import random
import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_adapter = HTTPAdapter(max_retries=Retry(
    total=3, connect=3, backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
EM_SESSION.mount("https://", _em_adapter)
EM_SESSION.mount("http://", _em_adapter)

# 最小请求间隔（秒）。批量筛选场景可调大到 1.5~2
EM_MIN_INTERVAL = 1.0
_em_last_call = 0.0
_em_lock = threading.Lock()  # FastAPI 多线程环境下保证串行限流


def _em_request(method: str, url: str, params: Optional[dict] = None,
                headers: Optional[dict] = None, timeout: int = 15, **kwargs):
    """东财统一请求入口，GET/POST 共用同一个串行限流器。"""
    global _em_last_call
    with _em_lock:
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call)
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
        try:
            return EM_SESSION.request(method, url, params=params, headers=headers,
                                      timeout=timeout, **kwargs)
        finally:
            _em_last_call = time.time()


def em_get(url: str, params: Optional[dict] = None,
           headers: Optional[dict] = None, timeout: int = 15, **kwargs):
    """东财 GET：自动节流 + 复用 session + 默认 UA。"""
    return _em_request("GET", url, params=params, headers=headers,
                       timeout=timeout, **kwargs)


def em_post(url: str, params: Optional[dict] = None,
            headers: Optional[dict] = None, timeout: int = 15, **kwargs):
    """东财 POST：与 GET 共享全局串行限流。"""
    return _em_request("POST", url, params=params, headers=headers,
                       timeout=timeout, **kwargs)


def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                         filter_str: str = "", page_size: int = 50,
                         sort_columns: str = "", sort_types: str = "-1") -> list:
    """东财数据中心统一查询 —— 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用。"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []
