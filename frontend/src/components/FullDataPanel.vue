<!--
  FullDataPanel.vue —— 全维度数据面板（零 token）
  查询个股后自动发起数据采集（后台任务），轮询完成后展示全部十二章数据：
  行情/赛道/估值/财务/筹码/情绪/解禁/研报/公告/综合评估 + 互动/热度附录。
  数据以确定性 Markdown 表格渲染（与 AI 报告的 data_md 同源），不调 AI。
-->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { collectData, fetchDataStatus, fetchFullData } from '../api/client.js'

const props = defineProps({
  code: { type: String, required: true },
})

const task = ref(null)      // 采集任务状态
const data = ref(null)      // 完整数据（十二章 data_md + 原始快照）
const error = ref('')
const polling = ref(false)
const timedOut = ref(false)
let timer = null
let controller = null
let pollStartedAt = 0

const chapters = computed(() => data.value?.chapters || [])
// 默认折叠数据量大的章节，其余全部展开，保证数据都在页面上
const COLLAPSED_BY_DEFAULT = ['ch4_finance', 'ch5_chips', 'ch9_notice', 'appx_a_interaction']
const sourceErrors = computed(() => Object.entries(data.value?.source_errors || {}))

function renderMarkdown(value) {
  return DOMPurify.sanitize(marked.parse(value || ''))
}

function stopPolling() {
  if (timer) clearTimeout(timer)
  timer = null
  polling.value = false
  if (controller) controller.abort()
  controller = null
}

async function loadData() {
  controller = new AbortController()
  data.value = await fetchFullData(props.code, controller.signal)
  task.value = { ...(task.value || {}), status: 'done' }
}

async function pollStatus() {
  if (!polling.value) return
  // 采集要并发抓 19 路数据源，给足 10 分钟等待窗口
  if (Date.now() - pollStartedAt > 10 * 60 * 1000) {
    timedOut.value = true
    polling.value = false
    return
  }
  try {
    controller = new AbortController()
    const status = await fetchDataStatus(props.code, controller.signal)
    task.value = status
    if (status.status === 'done') {
      polling.value = false
      await loadData()
      return
    }
    if (status.status === 'failed') {
      polling.value = false
      error.value = status.error || '数据采集失败'
      return
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message
  }
  if (polling.value) timer = setTimeout(pollStatus, 2500)
}

function beginPolling() {
  stopPolling()
  timedOut.value = false
  polling.value = true
  pollStartedAt = Date.now()
  pollStatus()
}

async function startCollect(refresh = false) {
  stopPolling()
  error.value = ''
  timedOut.value = false
  if (refresh) data.value = null
  try {
    controller = new AbortController()
    const result = await collectData(props.code, refresh, controller.signal)
    task.value = result
    if (result.status === 'done' && result.cached) {
      await loadData()
    } else {
      beginPolling()
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message
  }
}

watch(() => props.code, () => {
  stopPolling()
  task.value = null
  data.value = null
  error.value = ''
  timedOut.value = false
  startCollect(false)
})

onMounted(() => startCollect(false))
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="card full-data-panel">
    <div class="report-title-row">
      <div class="card-title">📊 全维度数据 <span class="muted">（零 token · 全部原始数据）</span></div>
      <button v-if="data" class="btn btn-ghost report-refresh" @click="startCollect(true)">重新采集</button>
    </div>

    <!-- 采集中：显示当前正在抓的数据源 -->
    <div v-if="polling || (task && !data && !error)" class="report-progress">
      <div class="progress-heading">
        <span>正在并发采集全维度数据…</span>
      </div>
      <p v-if="task?.current_chapter" class="muted">{{ task.current_chapter }}</p>
      <p class="muted">首次采集约需 30-60 秒（19 路数据源），完成后当日缓存秒开</p>
    </div>

    <div v-if="timedOut" class="warning-box">
      前端已停止等待，但后端采集仍会继续。点击“继续查看进度”恢复轮询。
      <button class="btn btn-ghost" @click="beginPolling">继续查看进度</button>
    </div>
    <div v-if="error" class="error-box">
      {{ error }}
      <button class="btn btn-ghost" @click="startCollect(false)">重试采集</button>
    </div>

    <template v-if="data">
      <div class="report-meta">
        <span class="tag">{{ data.cached ? '当日缓存' : '实时采集' }}</span>
        <span class="muted">采集时间：{{ data.fetched_at }}</span>
      </div>

      <!-- 数据源失败明细：哪些源没拿到数据一目了然 -->
      <div v-if="sourceErrors.length" class="warning-box">
        以下数据源未获取（不影响其余章节）：
        <div v-for="[source, message] in sourceErrors" :key="source" class="muted" style="font-size: 12px">
          · {{ source }}：{{ message }}
        </div>
      </div>

      <nav class="chapter-nav" aria-label="数据目录">
        <a v-for="chapter in chapters" :key="chapter.key" :href="`#data-${chapter.key}`">
          {{ chapter.title }}
        </a>
      </nav>

      <article class="report-body">
        <section
          v-for="chapter in chapters"
          :id="`data-${chapter.key}`"
          :key="chapter.key"
          class="chapter-section"
        >
          <h2>{{ chapter.title }}</h2>
          <details :open="!COLLAPSED_BY_DEFAULT.includes(chapter.key)">
            <summary>查看本章全部数据</summary>
            <div v-html="renderMarkdown(chapter.data_md)"></div>
          </details>
        </section>
      </article>
    </template>
  </section>
</template>
