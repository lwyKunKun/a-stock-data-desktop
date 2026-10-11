"""巨潮公告、互动易与上证 e 互动数据源。"""
from datetime import datetime
import html
import re

import requests

from app.core.cache import cached
from app.core.em_client import UA
from app.core.ticker import get_prefix, norm_ticker

_CNINFO_ORGID_MAP = {}
_SSE_BASE = "https://sns.sseinfo.com"
_SSE_UID_CACHE = {}
_SSE_COMPANY_PAGES = {}
_SSE_EMPTY_NOTE = re.compile(r'class="m_feed_note"[^>]*>[^<]*(暂无|暂时没有)[^<]*<')


def _cninfo_orgid(code: str) -> str:
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        response = requests.get(
            "http://www.cninfo.com.cn/new/data/szse_stock.json",
            headers={"User-Agent": UA}, timeout=15,
        )
        response.raise_for_status()
        stock_list = (response.json() or {}).get("stockList")
        if stock_list is None:
            raise RuntimeError("巨潮股票映射返回结构缺少 stockList")
        _CNINFO_ORGID_MAP = {row["code"]: row["orgId"] for row in stock_list}
    return _CNINFO_ORGID_MAP.get(code) or f"gs{get_prefix(code)}0{code}"


@cached("cninfo_announcements", until_eod=True)
def cninfo_announcements(code: str, page_size: int = 30) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    response = requests.post(
        "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        data={"stock": f"{code},{_cninfo_orgid(code)}", "tabName": "fulltext",
              "pageSize": str(page_size), "pageNum": "1", "column": "", "category": "",
              "plate": "", "seDate": "", "searchkey": "", "secid": "",
              "sortName": "", "sortType": "", "isHLtitle": "true"},
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": "https://www.cninfo.com.cn/new/disclosure",
                 "Origin": "https://www.cninfo.com.cn"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json() or {}
    announcements = payload.get("announcements")
    if announcements is None:
        raise RuntimeError("巨潮公告返回结构缺少 announcements")
    rows = []
    for item in announcements:
        timestamp = item.get("announcementTime")
        day = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d") if isinstance(timestamp, (int, float)) else str(timestamp or "")[:10]
        rows.append({"title": item.get("announcementTitle") or "",
                     "type": item.get("announcementTypeName") or "", "date": day,
                     "url": ("https://www.cninfo.com.cn/new/disclosure/detail?annoId="
                             f"{item.get('announcementId') or ''}")})
    return rows


@cached("cninfo_irm", until_eod=True)
def cninfo_irm(code: str, page_size: int = 15, page_num: int = 1) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    lookup = requests.post(
        "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
        data={"keyWord": code}, headers={"User-Agent": UA}, timeout=10,
    )
    lookup.raise_for_status()
    data = (lookup.json() or {}).get("data")
    if data is None:
        raise RuntimeError("互动易代码查询返回结构缺少 data")
    if not data:
        return []
    org_id = data[0].get("secid")
    response = requests.post(
        "https://irm.cninfo.com.cn/newircs/company/question",
        params={"_t": 1, "stockcode": code, "orgId": org_id, "pageSize": page_size,
                "pageNum": page_num, "keyWord": "", "startDay": "", "endDay": ""},
        headers={"User-Agent": UA}, timeout=10,
    )
    response.raise_for_status()
    payload = response.json() or {}
    rows = payload.get("rows")
    if rows is None:
        raise RuntimeError("互动易问答返回结构缺少 rows")
    result = []
    for item in rows:
        published = item.get("pubDate")
        result.append({"code": item.get("stockCode") or code,
                       "company": item.get("companyShortName") or "",
                       "question": item.get("mainContent") or "",
                       "answer": item.get("attachedContent"),
                       "answerer": item.get("attachedAuthor") or "",
                       "ask_time": datetime.fromtimestamp(published / 1000).strftime("%Y-%m-%d %H:%M")
                       if published else ""})
    return result


def _plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _sse_time(text: str):
    match = re.search(r"(\d{4})年(\d{2})月(\d{2})日\s*(\d{2}:\d{2})", text)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)} {match.group(4)}" if match else None


def _sse_company_page(page: int) -> list[tuple[str, str]]:
    if page not in _SSE_COMPANY_PAGES:
        response = requests.post(
            f"{_SSE_BASE}/allcompany.do",
            data={"code": "0", "order": "2", "areaId": "0", "page": page},
            headers={"User-Agent": UA, "Referer": f"{_SSE_BASE}/"}, timeout=15,
        )
        response.raise_for_status()
        content = (response.json() or {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"上证 e 互动公司列表第 {page} 页缺少 content")
        pairs = [(code, uid) for uid, code in re.findall(
            r"uid=['\"]?(\d+)['\"]?[^>]*>\s*<img[^>]*company/(\d{6})\.png", content
        )]
        if not pairs and page == 1:
            raise RuntimeError("上证 e 互动公司列表无法解析")
        _SSE_COMPANY_PAGES[page] = pairs
        _SSE_UID_CACHE.update(dict(pairs))
    return _SSE_COMPANY_PAGES[page]


def _sse_company_uid(code: str) -> str:
    if code in _SSE_UID_CACHE:
        return _SSE_UID_CACHE[code]
    low, high = 1, 1
    while True:
        pairs = _sse_company_page(high)
        if not pairs or pairs[-1][0] >= code:
            break
        low, high = high + 1, high * 2
    while low <= high:
        mid = (low + high) // 2
        pairs = _sse_company_page(mid)
        if not pairs or code < pairs[0][0]:
            high = mid - 1
        elif code > pairs[-1][0]:
            low = mid + 1
        else:
            break
    if code not in _SSE_UID_CACHE:
        raise ValueError(f"上证 e 互动没有 {code}")
    return _SSE_UID_CACHE[code]


def _parse_sse_feed(text: str) -> list[dict]:
    rows = []
    for chunk in re.split(r'<div class="m_feed_item[^"]*" id="item-', text)[1:]:
        item_id = re.match(r"(\d+)", chunk)
        if not item_id:
            raise RuntimeError("上证 e 互动条目 ID 结构改变")
        ask_part, _, answer_part = chunk.partition('class="m_feed_detail m_qa"')
        question = re.search(
            r'<div class="m_feed_txt"[^>]*>\s*<a[^>]*>:(.*?)\((\d{6})\)</a>(.*?)</div>',
            ask_part, re.S,
        )
        ask_time = re.search(r'<div class="m_feed_from"[^>]*>\s*<span>([^<]+)</span>', ask_part)
        if not question or not ask_time:
            raise RuntimeError(f"上证 e 互动第 {item_id.group(1)} 条无法解析")
        answer = answer_time = None
        if answer_part:
            body = re.search(r'<div class="m_feed_txt"[^>]*>(.*?)</div>', answer_part, re.S)
            when = re.search(r'<div class="m_feed_from"[^>]*>\s*<span>([^<]+)</span>', answer_part)
            if not body or not when:
                raise RuntimeError("上证 e 互动回复结构改变")
            answer, answer_time = _plain(body.group(1)), _sse_time(when.group(1))
        rows.append({"id": item_id.group(1), "code": question.group(2),
                     "company": _plain(question.group(1)), "question": _plain(question.group(3)),
                     "ask_time": _sse_time(ask_time.group(1)) or "",
                     "answer": answer, "answer_time": answer_time})
    return rows


@cached("sse_interaction", until_eod=True)
def sse_e_interaction(code: str, limit: int = 15) -> list[dict]:
    code = norm_ticker(code, stock_only=True)
    if get_prefix(code) != "sh":
        raise ValueError(f"{code} 不是沪市证券")
    response = requests.post(
        f"{_SSE_BASE}/ajax/userfeeds.do",
        data={"typeCode": "company", "type": 11, "pageSize": min(max(limit, 1), 50),
              "uid": _sse_company_uid(code), "page": 1},
        headers={"User-Agent": UA, "Referer": f"{_SSE_BASE}/"}, timeout=15,
    )
    response.raise_for_status()
    text = response.content.decode("utf-8", "replace")
    rows = _parse_sse_feed(text)
    if not rows and not _SSE_EMPTY_NOTE.search(text):
        raise RuntimeError("上证 e 互动响应既无问答也无空数据提示")
    if any(row["code"] != code for row in rows):
        raise RuntimeError("上证 e 互动返回了其他公司的问答")
    return rows


def investor_interaction(code: str, limit: int = 15) -> dict:
    code = norm_ticker(code, stock_only=True)
    prefix = get_prefix(code)
    if prefix == "sh":
        items, source = sse_e_interaction(code, limit), "sse_e"
    elif prefix == "sz":
        items, source = cninfo_irm(code, limit), "cninfo_irm"
    else:
        return {"source": "unsupported", "items": [], "available": False,
                "note": "北交所当前无公开投资者互动数据源"}
    answered = sum(1 for item in items if item.get("answer"))
    return {"source": source, "items": items,
            "answered_ratio": round(answered / len(items) * 100, 1) if items else 0}
