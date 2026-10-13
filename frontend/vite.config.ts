// Vite 构建配置
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 桌面端（tauri dev）sidecar 端口可用 DESKTOP_API_PORT 覆盖，默认 18000；
// 普通 Web 开发仍是 8000（DESKTOP_API_PORT 未设置时优先 8000 保持旧行为）
const apiTarget = process.env.DESKTOP_API_PORT
  ? `http://127.0.0.1:${process.env.DESKTOP_API_PORT}`
  : 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: true, // 监听 0.0.0.0，方便手机在同一局域网访问调试
    // 开发环境代理：前端请求 /api/* 转发到本地后端，规避跨域
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
