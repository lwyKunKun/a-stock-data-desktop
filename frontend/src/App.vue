<!--
  App.vue —— 应用主组件
  职责：搜索框 + 状态管理（当前股票、加载状态）+ 编排各展示组件
  数据流：输入代码 → 归一化校验拿到股票代码 → 全维度数据面板自动采集展示
          （全部十二章数据，零 token）→ 下方可选 AI 全维度分析（按次计费）
-->
<script setup lang="ts">
import { ref } from 'vue'
import { fetchSnapshot } from './api/client'
import { errorMessage } from './utils/errors'
import FullDataPanel from './components/FullDataPanel.vue'
import AiReport from './components/AiReport.vue'

const codeInput = ref<string>('')
const currentCode = ref<string>('')
const loading = ref<boolean>(false)
const error = ref<string>('')

const examples = ['600519', '300750', '002594', '688017'] as const

async function search(code?: string): Promise<void> {
  const target = (code || codeInput.value).trim()
  if (!target) return
  loading.value = true
  error.value = ''
  currentCode.value = ''
  try {
    const snapshot = await fetchSnapshot(target)
    currentCode.value = snapshot.code
  } catch (caught: unknown) {
    error.value = errorMessage(caught)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="container">
    <!-- 顶部标题 -->
    <header style="padding: 8px 4px 16px">
      <h1 style="font-size: 20px">📈 A股数据看板</h1>
      <p class="muted">普通查询零成本 · 全维度数据全量展示 · AI 分析按次计费</p>
    </header>

    <!-- 搜索区 -->
    <div class="card">
      <div style="display: flex; gap: 8px">
        <input
          v-model="codeInput"
          class="input"
          placeholder="输入股票代码，如 600519（支持 sh600519 / 600519.SH）"
          @keyup.enter="search()"
        />
        <button class="btn btn-primary" :disabled="loading" @click="search()">
          查询
        </button>
      </div>
      <!-- 示例快捷入口 -->
      <div class="tags" style="margin-top: 10px">
        <span
          v-for="ex in examples"
          :key="ex"
          class="tag"
          style="cursor: pointer"
          @click="search(ex)"
        >{{ ex }}</span>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-box">❌ {{ error }}</div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">
      <span class="spinner"></span>正在校验股票代码…
    </div>

    <!-- 数据展示区：全维度数据面板（自动采集全部十二章）+ AI 分析 -->
    <template v-if="currentCode && !loading">
      <FullDataPanel :code="currentCode" />

      <!-- AI 分析：独立组件，可自动或手动触发 -->
      <AiReport :code="currentCode" />
    </template>
  </div>
</template>
