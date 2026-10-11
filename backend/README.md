# stock-app backend

FastAPI A 股数据服务与十二章 AI 个股报告后端。结构化查询零 token；完整报告使用后台任务分章调用 DeepSeek，并按日落盘缓存。

## 启动

```bash
cd ~/stock-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

交互式文档：`http://127.0.0.1:8000/docs`。

## 配置

在 `backend/.env` 配置：

```dotenv
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
PORT=8000

REPORT_AI_CONCURRENCY=3
REPORT_CHAPTER_MAX_TOKENS=800
REPORT_FINAL_MAX_TOKENS=2500
REPORT_AI_TIMEOUT=180
REPORT_AI_RETRIES=2
REPORT_TASK_STALE_SECONDS=600
REPORT_AUTO_TRIGGER=0

OBSIDIAN_SYNC=1
OBSIDIAN_VAULT_PATH=/Users/leiwanyue/Documents/Obsidian Vault
STOCK_REVIEW_PUBLISH=1
STOCK_REVIEW_PATH=/Users/leiwanyue/stock-review
STOCK_REVIEW_DEPLOY_SCRIPT=/Users/leiwanyue/stock-review/deploy.sh
```

`REPORT_AUTO_TRIGGER=0` 表示首次默认手动生成；前端用户选择会保存到 localStorage。测试环境应关闭 `OBSIDIAN_SYNC` 和 `STOCK_REVIEW_PUBLISH`，避免外部副作用。

## 报告 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/report/config` | 前端默认模式、章节清单与发布能力 |
| `POST` | `/api/report/{code}/generate` | Body `{"refresh": false}`；创建任务或返回当日缓存 |
| `GET` | `/api/report/{code}/status` | 查询阶段、十二章状态和进度 |
| `GET` | `/api/report/{code}` | 返回结构化报告 JSON |
| `GET` | `/api/report/{code}/markdown` | 返回完整 Markdown |
| `POST` | `/api/report/{code}/chapter/{key}/retry` | 异步重试单章点评 |
| `POST` | `/api/report/{code}/publish/retry` | 只重试 Obsidian/Git/部署链路 |

旧 `/api/ai_analysis/{code}` 暂时保留兼容。行情、估值、资金流、概念和轻量快照端点保持不变。

## 十二章数据来源

- 腾讯：实时行情、PE/PB、市值、涨跌停价格。
- 同花顺：一致预期 EPS、热榜。
- 新浪：利润表、资产负债表、现金流量表；日资金流备胎。
- 东财：概念板块、研报、两融、大宗、股东户数、分红、资金流、龙虎榜、解禁、涨跌停池和人气榜。
- 巨潮：公告、深市互动易。
- 上证 e 互动：沪市投资者问答。

所有东财 GET/POST 请求共享 `em_client.py` 的串行限流器。单源失败会记录在章节中，不会拖垮整份报告；真正空数据与网络/结构错误分开处理。

## 生成与发布

1. `full_aggregator.py` 聚合并按十二章裁剪数据。
2. `chapter_md.py` 由 Python 生成数值表格；AI 不负责抄写数字。
3. 第一至九章和两个附加章生成引用块点评；第十章最后生成综合评估。
4. 状态写入 `data/tasks/{code}.json`，报告写入 `data/reports/{date}_{code}.json/.md`。
5. 完成后写入 Obsidian 股票基本面目录和当日日志。
6. 精确复制报告与日志到 stock-review，只暂存本次两个文件，提交、推送，再执行现有 `deploy.sh`。

外部发布失败时任务为 `done_with_warnings`，应用缓存仍可查看，并可单独重试发布。

## 测试

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests
```

测试覆盖数据源解析、十二章 Markdown、分章生成、文件任务状态、分类规则和发布链路。Git、推送和部署在测试中全部使用 mock，不会操作真实仓库。
