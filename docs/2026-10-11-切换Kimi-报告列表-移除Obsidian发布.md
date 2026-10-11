# 2026-10-11 切换 Kimi For Coding 订阅 API、新增报告列表、移除 Obsidian 发布

## 一、LLM 平台切换为 Kimi For Coding 订阅

### 背景
原配置使用 DeepSeek。用户改用 Kimi For Coding 订阅（kimi.com 会员的 API Keys）。

### 实测发现的平台差异（重要）
- `sk-kimi-` 开头的 key **不走** `api.moonshot.cn` / `api.moonshot.ai`，实测两个官方端点均返回 `Invalid Authentication`；正确端点是 **`https://api.kimi.com/coding/v1`**（OpenAI 兼容）
- `kimi-k2-0711-preview` 是推理模型，**只接受 `temperature=1`**，传其他值报 `invalid temperature: only 1 is allowed for this model`
- 返回的 usage 带 `completion_tokens_details.reasoning_tokens` 等嵌套结构，既有 `_usage_total()` 修复已兼容

### 修改
- `backend/.env`：`DEEPSEEK_*` 三项整体替换为 `LLM_PROVIDER=Kimi` / `LLM_API_KEY` / `LLM_BASE_URL=https://api.kimi.com/coding/v1` / `LLM_MODEL=kimi-k2-0711-preview` / `LLM_TEMPERATURE=1`；移除 DEEPSEEK_* 回退逻辑（不再需要）
- `app/core/config.py`：默认 base_url/model 改为 Kimi；`llm_provider_name` 识别 `kimi`/`moonshot` host 显示「Kimi」；新增 `LLM_TEMPERATURE`（默认 0.3）
- `app/services/llm_client.py`：`chat()` 的 temperature 参数改为 Optional，缺省走 `settings.LLM_TEMPERATURE`；调用方（`report_generator.py` 4 处、`ai_analyst.py` 1 处）不再显式传 temperature

### 验证
- 用应用自身 `llm_client.chat()` 真实调用 Kimi：正文非空、usage 结构正常（`completion_tokens_details` 嵌套 dict 被 `_usage_total` 正确跳过）
- 17 项 pytest 全部通过

## 二、已生成报告列表模块

### 存储方案：SQLite 轻量索引（用户选择）
报告正文仍按天存 JSON（`backend/data/reports/`），另建 `backend/data/reports_index.db` 只存 meta 级字段（代码/名称/日期/行业/模型/tokens/耗时/价格/涨跌幅/PE），支撑组合筛选。Python 内置 sqlite3，零新增依赖。

### 后端
- 新增 `app/services/report_index.py`：建表、`upsert_report`（同股同天覆盖）、`backfill`（扫描 reports/ 目录一次性回填历史，幂等只跑一次）、`list_reports`（date/industry 筛选 + 返回可选筛选项）
- `app/services/report_task.py`：`_save_report` 同步写索引
- `app/api/report_routes.py`：新增 `GET /api/report/list?date=&industry=`

### 前端
- 新增 `frontend/src/components/ReportList.vue`：日期/行业下拉筛选 + 报告表格（股票/行业/现价/涨跌幅/PE/模型/tokens/耗时），点击行 emit 代码跳回该股票查询页
- `App.vue` 挂载于数据面板下方；`client.ts` 新增 `fetchReportList`

### 验证
- 实测 `/api/report/list`：自动回填历史报告（东岳硅材 300821，行业「化学制品」），行业筛选、日期筛选均正确

## 三、移除 Obsidian 发布链路

### 原因
用户认为上传到 Obsidian 的步骤多余，要求删除。

### 删除内容
- `app/services/report_publisher.py` 整个删除（Obsidian 写入、当日日志、stock-review 复制、git push、deploy.sh）
- `report_task.py`：`_run_generate` 保存报告后直接 `done`，不再有 `publishing` 阶段；删除 `_run_publish` / `retry_publish` / `_publication_ok`，`_ACTIVE_STATES` 移除 `publishing`；章节重试后同样直接 `done`
- `report_routes.py`：删除 `POST /{code}/publish/retry` 端点；`/config` 移除 obsidian_sync/stock_review_publish
- `config.py`：删除 `OBSIDIAN_*` / `STOCK_REVIEW_*` 五项设置
- 前端：`AiReport.vue` 删除发布状态框/重试发布按钮/相关 computed 与函数；`types.ts` 删除 `Publication*` 类型与 `publishing` 状态；`client.ts` 删除 `retryReportPublish`
- 测试：删除 `test_report_publisher.py`（2 项），任务测试同步更新
- README（根 + backend）同步更新

### 验证
- 17 项 pytest 全部通过
- 实测 `POST /api/report/300821/publish/retry` 返回 404（端点已移除）
- `vue-tsc --noEmit` + `npm run build` 全绿

## 备注
- `.env` 不入库（gitignore），换机部署时按 `backend/README.md` 模板重新填写
- 旧的 `done_with_warnings` 状态类型在前端类型中保留兼容（旧任务文件可能残留），后端不再产生
