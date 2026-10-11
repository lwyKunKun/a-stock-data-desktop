# stock-app frontend

Vue 3 + Vite 的 A 股数据看板，支持手机和电脑。行情卡片不调用大模型；AI 全维度报告支持自动/手动触发和当日缓存。

## 启动

```bash
cd ~/stock-app/frontend
npm install
npm run dev
```

- 电脑访问 `http://localhost:5173`。
- 手机使用同一局域网下 Vite 输出的 Network 地址。
- 后端需运行在 8000 端口，开发环境通过 Vite 代理转发 `/api`。

## 报告交互

- 首次默认手动生成，避免意外产生 token 费用；可切换为进入详情页自动生成。
- 生成任务每 2.5 秒轮询一次，展示聚合、分章生成和发布阶段，以及十二章状态。
- 完成后按章节显示目录、锚点和可折叠长表。
- 单章点评失败可单独重试；Obsidian/Git/部署失败可只重试发布。
- 强制重新生成会二次确认。
- Markdown 经 `marked` 渲染并由 DOMPurify 清洗后才写入页面。

触发模式保存在浏览器 localStorage，切换股票或卸载组件时会取消旧轮询。

## 生产构建

```bash
npm run build
```

产物位于 `dist/`，由 Nginx 托管。报告进度使用普通短轮询，不依赖 SSE 或 WebSocket 配置。

## 主要文件

```text
src/
├── App.vue                    搜索与卡片编排
├── api/client.js              轻量查询和报告任务 API
├── components/AiReport.vue    自动/手动、轮询、分章、失败恢复
└── style.css                  响应式卡片、进度和报告表格样式
```
