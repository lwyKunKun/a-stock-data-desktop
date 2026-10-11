// Vite 构建配置
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: true, // 监听 0.0.0.0，方便手机在同一局域网访问调试
    // 开发环境代理：前端请求 /api/* 转发到后端 8000，规避跨域
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
