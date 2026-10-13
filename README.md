# a-stock-data-desktop

A 股数据看板与全维度 AI 个股报告工具。普通行情查询零 token；完整报告按章节调用.env中自己配置的LLM，并按交易日缓存。

## 架构

```text
Vue 3 前端
├── 行情 / 估值 / 资金流 / 板块卡片
├── AI 报告：手动触发 → 任务轮询 → 摘要卡片（生成完成自动进入归档）
├── 报告归档：列表筛选分页 → 「代码 + 日期」只读详情，滚动侦测目录
└── 设置：LLM 接入配置（应用内设置页，Key 永不回显明文）
        │ /api
FastAPI 后端
├── 腾讯 / 东财 / 新浪 / 同花顺 / 巨潮 / 上证 e 互动
├── 十二章结构化聚合与确定性 Markdown 表格
├── LLM 分章点评 + 综合评估
├── 文件任务状态与按日报告归档（同日去重、跨天累积）
├── 报告 SQLite 索引与按日期/行业筛选归档
└── 用户级配置（数据目录 config.json，环境变量优先）
```

桌面端（Tauri）：Rust 壳拉起 PyInstaller 后端 sidecar，生产模式由后端直接托管前端静态文件，`/api` 相对路径零改造。详见 `docs/2026-10-13-Tauri桌面端打包.md`。

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

## 桌面端（macOS）

双击即用的 `.app`，无需安装 Python/Node。后端 PyInstaller 打成 sidecar 由 Tauri 壳自动拉起，数据与配置写在用户数据目录（`~/Library/Application Support/com.stockapp.desktop/`），与 Web 开发模式的 `backend/data/` 互相独立。

```bash
# 构建 dmg（详见 docs/2026-10-13-Tauri桌面端打包.md）
cd backend && .venv/bin/pyinstaller a_stock_desktop.spec --clean --noconfirm && cd ..
cp backend/dist/a_stock_desktop frontend/src-tauri/binaries/a_stock_desktop-x86_64-apple-darwin
cd frontend && cargo tauri build   # 产物 src-tauri/target/release/bundle/dmg/*.dmg
```

未签名，首次打开需右键 →「打开」。首次启动未配置 LLM 会自动进入设置页。

## 缓存与成本

- 行情卡片与结构化数据查询不调用大模型。
- 完整报告首次生成会产生多次分章调用；当日同股默认读取 `backend/data/reports/`，不重复消耗 token。
- 强制重新生成会重新调用 AI，前端会二次确认。
- 单章点评失败可单独重试，不重新生成整份报告。

## 前端体验与数据源监控

- 应用级侧边导航：「A股数据看板」「已生成的报告」「设置」为三个同级模块，侧边栏切换（窄屏退化为顶部横向导航）；报告归档点击股票名称进入该「代码 + 日期」的独立详情页，返回时保留列表筛选与分页状态。
- AI 报告全程手动触发：进入个股只读当日缓存，仅点击「生成全维度报告」才调用 AI 产生 token 费用；已移除手动/自动切换开关及后端对应配置。生成完成后自动切换到报告归档列表，看板下方只保留摘要卡片（章节状态、查看完整报告、重新生成），完整报告统一在归档详情中展示，不再内嵌重复。
- 报告详情页左侧目录带滚动侦测：右侧正文滚动时自动高亮并跟随当前章节。
- 当天报告的详情页支持单章重试（点评失败 / 数据失败的章节显示重试按钮，重试完成后自动刷新）；历史归档严格只读。
- 查询持久化：刷新页面自动恢复上次查询；查询历史保留最近 20 条（localStorage）。
- 已生成报告列表：SQLite 索引（`backend/data/reports_index.db`），使用中文日期选择器和行业筛选，采用服务端分页（默认每页 10 条）；即使只有一页也显示明确的页码状态。
- AI 报告中的数据源异常只显示简短摘要，完整网络错误和请求信息收进可折叠的技术详情，便于阅读且不丢失诊断信息。
- 数据源版本监控：上游 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) 有新提交时页面顶部提醒，可一键生成「已确认版本 → 最新版本」的函数级更新报告（映射到后端移植文件），移植完成后点「知道了」确认基线。
- 详见 `docs/` 下各更新记录。

## 验证

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests
npm --prefix frontend run build
```

详细接口、配置和数据源见 `backend/README.md`，前端交互见 `frontend/README.md`。
