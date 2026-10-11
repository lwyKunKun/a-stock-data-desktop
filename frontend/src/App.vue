<!--
  App.vue —— 应用主组件
  职责：搜索框 + 状态管理（当前股票、快照数据、加载状态）+ 编排各展示卡片
  数据流：输入代码 → 调 /api/snapshot 一次拿齐全维度数据 → 分发给各卡片组件
-->
<script setup>
import { ref } from 'vue'
import { fetchSnapshot } from './api/client.js'
import QuoteCard from './components/QuoteCard.vue'
import ValuationCard from './components/ValuationCard.vue'
import FundFlowCard from './components/FundFlowCard.vue'
import ConceptCard from './components/ConceptCard.vue'
import AiReport from './components/AiReport.vue'

// ── 响应式状态 ──
const codeInput = ref('')      // 搜索框输入
const snapshot = ref(null)     // 全维度快照数据
const loading = ref(false)     // 是否加载中
const error = ref('')          // 错误信息

// 常用示例，点击直接查询（方便测试）
const examples = ['600519', '300750', '002594', '688017']

// 查询个股全维度快照
async function search(code) {
  const target = (code || codeInput.value).trim()
  if (!target) return
  loading.value = true
  error.value = ''
  snapshot.value = null
  try {
    // 一次调用拿齐 行情/估值/资金流/板块（后端并发抓取）
    snapshot.value = await fetchSnapshot(target)
  } catch (e) {
    error.value = e.message
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
      <p class="muted">普通查询零成本 · AI 全维度分析按次计费</p>
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
      <span class="spinner"></span>正在并发抓取全维度数据…
    </div>

    <!-- 数据展示区：快照加载完成后渲染各卡片 -->
    <template v-if="snapshot && !loading">
      <QuoteCard :quote="snapshot.quote" :code="snapshot.code" />
      <ValuationCard :valuation="snapshot.valuation" />
      <FundFlowCard
        :minute="snapshot.fund_flow_minute"
        :daily="snapshot.fund_flow_daily"
      />
      <ConceptCard :concept="snapshot.concept" />

      <!-- AI 分析：独立组件，可自动或手动触发 -->
      <AiReport
        :code="snapshot.code"
        :name="snapshot.valuation?.name || snapshot.quote?.name || snapshot.code"
      />
    </template>
  </div>
</template>
