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
- 生成任务每 2.5 秒轮询一次，展示数据聚合、分章生成和十二章状态。
- 完成后按章节显示目录、锚点和可折叠长表；数据源异常只显示摘要，完整诊断信息放在折叠详情中。
- 已生成报告列表支持中文日期选择器、行业筛选和服务端分页；单页也显示明确的页码状态。
- 单章点评失败可单独重试，强制重新生成会二次确认。
- Markdown 经 `marked` 渲染并由 DOMPurify 清洗后才写入页面。

切换股票或卸载组件时会取消旧轮询和未完成请求。

## 生产构建

```bash
npm run build
```

产物位于 `dist/`，由 Nginx 托管。报告进度使用普通短轮询，不依赖 SSE 或 WebSocket 配置。

## 主要文件

```text
src/
├── App.vue                       应用级导航、搜索与视图编排
├── api/client.ts                 查询与报告任务 API
├── api/types.ts                  前后端数据类型
├── components/AiReport.vue       手动生成、轮询、分章与错误详情
├── components/ReportList.vue     日期/行业筛选与分页报告列表
└── style.css                     响应式布局、进度和报告样式
```
