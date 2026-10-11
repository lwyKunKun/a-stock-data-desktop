# a-stock-data-desktop

A 股数据看板与全维度 AI 个股报告工具。普通行情查询零 token；完整报告按章节调用 DeepSeek，并按交易日缓存。

## 架构

```text
Vue 3 前端
├── 行情 / 估值 / 资金流 / 板块卡片
└── AI 报告：手动触发 → 任务轮询 → 十二章分章展示
        │ /api
FastAPI 后端
├── 腾讯 / 东财 / 新浪 / 同花顺 / 巨潮 / 上证 e 互动
├── 十二章结构化聚合与确定性 Markdown 表格
├── DeepSeek 分章点评 + 综合评估
├── 文件任务状态与当日报告缓存
└── 报告 SQLite 索引与按日期/行业筛选归档
```

报告结构为十章主报告加两个附加章：实时行情、赛道定位、估值、财务、筹码、打板情绪、解禁、研报、公告、综合评估、投资者互动、热度。

## 启动

```bash
# 后端
cd ~/a-stock-data-desktop/backend
python3 -m venv --clear .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd ~/a-stock-data-desktop/frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`，API 文档位于 `http://127.0.0.1:8000/docs`。

## 缓存与成本

- 行情卡片与结构化数据查询不调用大模型。
- 完整报告首次生成会产生多次分章调用；当日同股默认读取 `backend/data/reports/`，不重复消耗 token。
- 强制重新生成会重新调用 AI，前端会二次确认。
- 单章点评失败可单独重试，不重新生成整份报告。

## 前端体验与数据源监控

- 应用级侧边导航：「A股数据看板」与「已生成的报告」为两个同级模块，侧边栏切换（窄屏退化为顶部横向导航）；报告归档点击行即切回看板并查询该股票。
- AI 报告全程手动触发：进入个股只读当日缓存，仅点击「生成全维度报告」才调用 AI 产生 token 费用；已移除手动/自动切换开关及后端对应配置。
- 查询持久化：刷新页面自动恢复上次查询；查询历史保留最近 20 条（localStorage）。
- 已生成报告列表：SQLite 索引（`backend/data/reports_index.db`），使用中文日期选择器和行业筛选，采用服务端分页（默认每页 10 条），点击行跳回该股票当日报告。
- 数据源版本监控：上游 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) 有新提交时页面顶部提醒，可一键生成「已确认版本 → 最新版本」的函数级更新报告（映射到后端移植文件），移植完成后点「知道了」确认基线。
- 详见 `docs/` 下各更新记录。

## 验证

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests
npm --prefix frontend run build
```

详细接口、配置和数据源见 `backend/README.md`，前端交互见 `frontend/README.md`。
