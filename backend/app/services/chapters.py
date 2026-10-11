"""全维度报告章节定义。"""

CHAPTERS = [
    {"key": "ch1_quote", "title": "一、实时行情"},
    {"key": "ch2_track", "title": "二、赛道定位"},
    {"key": "ch3_valuation", "title": "三、估值分析"},
    {"key": "ch4_finance", "title": "四、财务数据"},
    {"key": "ch5_chips", "title": "五、筹码面"},
    {"key": "ch6_sentiment", "title": "六、打板情绪"},
    {"key": "ch7_unlock", "title": "七、解禁预警"},
    {"key": "ch8_research", "title": "八、研报摘要"},
    {"key": "ch9_notice", "title": "九、重要公告"},
    {"key": "ch10_summary", "title": "十、综合评估"},
    {"key": "appx_a_interaction", "title": "附加A、投资者互动"},
    {"key": "appx_b_hot", "title": "附加B、热度"},
]

CHAPTER_KEYS = tuple(chapter["key"] for chapter in CHAPTERS)
CHAPTER_TITLES = {chapter["key"]: chapter["title"] for chapter in CHAPTERS}
COMMENT_CHAPTER_KEYS = tuple(key for key in CHAPTER_KEYS if key != "ch10_summary")


def initial_chapter_states() -> list[dict]:
    return [
        {"key": chapter["key"], "title": chapter["title"], "state": "pending"}
        for chapter in CHAPTERS
    ]
