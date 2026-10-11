# a-stock-data-desktop

A 股数据看板与全维度 AI 个股报告工具。普通行情查询零 token；完整报告按章节调用 DeepSeek，并按交易日缓存。

## 架构

```text
Vue 3 前端
├── 行情 / 估值 / 资金流 / 板块卡片
└── AI 报告：自动或手动触发 → 任务轮询 → 十二章分章展示
        │ /api
FastAPI 后端
├── 腾讯 / 东财 / 新浪 / 同花顺 / 巨潮 / 上证 e 互动
├── 十二章结构化聚合与确定性 Markdown 表格
├── DeepSeek 分章点评 + 综合评估
├── 文件任务状态与当日报告缓存
└── Obsidian → stock-review → GitHub → 阿里云部署
```

报告结构为十章主报告加两个附加章：实时行情、赛道定位、估值、财务、筹码、打板情绪、解禁、研报、公告、综合评估、投资者互动、热度。

## 启动

```bash
# 后端
cd ~/stock-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd ~/stock-app/frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`，API 文档位于 `http://127.0.0.1:8000/docs`。

## 缓存与成本

- 行情卡片与结构化数据查询不调用大模型。
- 完整报告首次生成会产生多次分章调用；当日同股默认读取 `backend/data/reports/`，不重复消耗 token。
- 强制重新生成会重新调用 AI，前端会二次确认。
- 单章点评失败可单独重试；发布失败可只重试发布，不重新生成报告。

## 验证

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests
npm --prefix frontend run build
```

详细接口、配置和数据源见 `backend/README.md`，前端交互见 `frontend/README.md`。
