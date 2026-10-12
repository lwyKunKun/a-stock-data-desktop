# stock-app frontend

Vue 3 + Vite 的 A 股数据看板，支持手机和电脑。行情卡片不调用大模型；AI 全维度报告全程手动触发并按交易日读取缓存。

## 启动

```bash
cd ~/a-stock-data-desktop/frontend
npm install
npm run dev
```

- 电脑访问 `http://localhost:5173`。
- 手机使用同一局域网下 Vite 输出的 Network 地址。
- 后端需运行在 8000 端口，开发环境通过 Vite 代理转发 `/api`。

## 报告交互

- AI 报告全程手动生成，避免浏览个股时意外产生 token 费用；已有当日缓存会自动读取。
- 生成任务每 2.5 秒轮询一次，展示数据聚合、分章生成和十二章状态；完成后自动切换到「已生成的报告」归档列表。
- 看板上的 AI 区块只显示摘要卡片：章节状态、失败章节重试、「查看完整报告」跳转归档详情、「重新生成」（二次确认），不再内嵌完整报告。
- 归档详情按「代码 + 日期」精确读取：历史日期严格只读；当天报告的失败章节（点评失败 / 数据失败）可单独重试，重试完成后自动刷新展示。
- 完整报告含目录锚点、可折叠长表和滚动侦测高亮：右侧正文滚动时左侧目录自动跟随当前章节；数据源异常只显示摘要，完整诊断信息放在折叠详情中。
- 已生成报告列表支持中文日期选择器、行业筛选和服务端分页；单页也显示明确的页码状态。
- Markdown 经 `marked` 渲染并由 DOMPurify 清洗后才写入页面。

切换股票、切换详情目标或卸载组件时会取消旧轮询和未完成请求。

## 生产构建

```bash
npm run build
```

产物位于 `dist/`，由 Nginx 托管。报告进度使用普通短轮询，不依赖 SSE 或 WebSocket 配置。

## 主要文件

```text
src/
├── App.vue                       应用级导航、搜索与视图编排（看板 / 归档列表 / 归档详情）
├── api/client.ts                 查询与报告任务 API（报告读取支持按日期）
├── api/types.ts                  前后端数据类型
├── components/AiReport.vue       手动生成、轮询、摘要卡片与失败章节重试
├── components/ReportList.vue     日期/行业筛选与分页报告列表
├── components/ReportViewer.vue   纯展示：Markdown 渲染、目录滚动侦测、章节重试入口
├── components/ReportDetail.vue   「代码 + 日期」只读归档详情（当天报告允许章节重试）
└── style.css                     响应式布局、进度和报告样式
```
