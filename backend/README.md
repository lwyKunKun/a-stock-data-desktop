# stock-app backend

FastAPI A 股数据服务与十二章 AI 个股报告后端。结构化查询零 token；完整报告使用后台任务分章调用 LLM（当前为 Kimi For Coding 订阅），按日落盘缓存并建立 SQLite 索引。

## 启动

```bash
cd ~/a-stock-data-desktop/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

交互式文档：`http://127.0.0.1:8000/docs`。

## 配置

在 `backend/.env` 配置：

```dotenv
# LLM 平台（OpenAI 兼容接口，可整体替换：Kimi / DeepSeek / 千问 Token Plan / 百炼 / OpenAI 等）
# 当前使用 Kimi For Coding 订阅（kimi.com → API Keys 页面获取 key）
LLM_PROVIDER=Kimi
LLM_API_KEY=sk-kimi-xxxx
LLM_BASE_URL=https://api.kimi.com/coding/v1
LLM_MODEL=kimi-k2-0711-preview
LLM_TEMPERATURE=1   # Kimi K2 只接受 1；其他平台可删此行或改 0.3
PORT=8000

REPORT_AI_CONCURRENCY=3
REPORT_CHAPTER_MAX_TOKENS=800
REPORT_FINAL_MAX_TOKENS=2500
REPORT_AI_TIMEOUT=180
REPORT_AI_RETRIES=2
REPORT_TASK_STALE_SECONDS=600
```

LLM 配置实际生效优先级：**环境变量（含 .env） > 数据目录 `config.json`**（设置页写入）。桌面端无 .env，靠前端「设置」页生成 config.json；`from_env=true` 时设置页保存不生效（页面有提示）。

桌面端（Tauri sidecar）专用环境变量，均由壳注入、无需手配：

| 变量 | 作用 |
|---|---|
| `APP_DATA_DIR` | 数据目录覆盖；默认 `backend/data/`。桌面端指向用户数据目录（`~/Library/Application Support/com.stockapp.desktop/`） |
| `SERVE_STATIC_DIR` | 设置时由本服务直接托管前端 dist（桌面端窗口加载 `http://127.0.0.1:端口/`） |
| `SHELL_LOCK_PATH` | sidecar flock 探活锁文件；锁释放（壳死亡）即自杀，防孤儿进程 |

## 报告 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/report/list` | 已生成报告列表（SQLite 索引）；返回 `source`（`desktop` / `web` / 历史记录 `null`），支持 Query `date` / `industry` 筛选及 `page` / `page_size` 分页（默认 1 / 10） |
| `POST` | `/api/report/{code}/generate` | Body `{"refresh": false, "source": "web"}`；`source` 只接受 `desktop` / `web`，创建任务或返回当日缓存 |
| `GET` | `/api/report/{code}/status` | 查询阶段、十二章状态和进度 |
| `GET` | `/api/report/{code}` | 返回结构化报告 JSON；Query `date=YYYY-MM-DD` 读取历史归档，缺省读当天 |
| `GET` | `/api/report/{code}/markdown` | 返回完整 Markdown |
| `POST` | `/api/report/{code}/chapter/{key}/retry` | 异步重试单章点评 |

## 设置 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/settings` | LLM 设置状态；Key 只回脱敏掩码，绝不外显明文 |
| `PUT` | `/api/settings` | Body 可含 `llm_api_key` / `llm_base_url` / `llm_model` / `llm_temperature`（均可选，合并写入数据目录 `config.json`） |

旧 `/api/ai_analysis/{code}` 暂时保留兼容。行情、估值、资金流、概念和轻量快照端点保持不变。

## 十二章数据来源

- 腾讯：实时行情、PE/PB、市值、涨跌停价格。
- 同花顺：一致预期 EPS、热榜。
- 新浪：利润表、资产负债表、现金流量表；日资金流备胎。
- 东财：概念板块、研报、两融、大宗、股东户数、分红、资金流、龙虎榜、解禁、涨跌停池和人气榜。
- 巨潮：公告、深市互动易。
- 上证 e 互动：沪市投资者问答。

所有东财 GET/POST 请求共享 `em_client.py` 的串行限流器。单源失败会记录在章节中，不会拖垮整份报告；真正空数据与网络/结构错误分开处理。

## 生成与存储

1. `full_aggregator.py` 聚合并按十二章裁剪数据。
2. `chapter_md.py` 由 Python 生成数值表格；AI 不负责抄写数字。
3. 第一至九章和两个附加章生成引用块点评；第十章最后生成综合评估。
4. 状态写入 `data/tasks/{code}.json`，报告写入 `data/reports/{date}_{code}.json/.md`。
5. `report_index.py` 同步维护 `data/reports_index.db`（SQLite），支撑列表页按日期/行业筛选；首次列表查询自动回填历史报告。
6. 真正生成成功时将请求中的 `source` 写入报告 JSON 和 SQLite；读取缓存、查看报告或重试单章不会改变来源，旧报告显示为未知。旧索引库首次打开时会自动增加 nullable `source` 列。

## 测试

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests
```

测试覆盖数据源解析、十二章 Markdown、分章生成、文件任务状态、报告索引和分类规则。
