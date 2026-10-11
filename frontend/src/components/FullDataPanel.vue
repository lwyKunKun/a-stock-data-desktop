<!--
  FullDataPanel.vue —— 全维度数据面板（零 token）
  查询个股后自动发起数据采集（后台任务），轮询完成后展示全部十二章数据：
  行情/赛道/估值/财务/筹码/情绪/解禁/研报/公告/综合评估 + 互动/热度附录。
  数据以确定性 Markdown 表格渲染（与 AI 报告的 data_md 同源），不调 AI。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { collectData, fetchDataStatus, fetchFullData } from '../api/client'
import type { DataChapter, DataTaskStatus, FullDataResponse } from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

const props = defineProps<{ code: string }>()

const task = ref<DataTaskStatus | null>(null)
const data = ref<FullDataResponse | null>(null)
const error = ref<string>('')
const polling = ref<boolean>(false)
const timedOut = ref<boolean>(false)
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null
let pollStartedAt = 0

const chapters = computed<DataChapter[]>(() => data.value?.chapters ?? [])
const COLLAPSED_BY_DEFAULT: ReadonlySet<string> = new Set([
  'ch4_finance',
  'ch5_chips',
  'ch9_notice',
  'appx_a_interaction',
])
const sourceErrors = computed<Array<[string, string]>>(
  () => Object.entries(data.value?.source_errors ?? {}),
)

function renderMarkdown(value: string): string {
  const html = marked.parse(value || '', { async: false })
  if (typeof html !== 'string') throw new Error('Markdown 渲染器返回了异步结果')
  return DOMPurify.sanitize(html)
}

function stopPolling(): void {
  if (timer) clearTimeout(timer)
  timer = null
  polling.value = false
  controller?.abort()
  controller = null
}

async function loadData(): Promise<void> {
  controller = new AbortController()
  data.value = await fetchFullData(props.code, controller.signal)
  task.value = {
    ...(task.value ?? { code: props.code }),
    status: 'done',
  }
}

async function pollStatus(): Promise<void> {
  if (!polling.value) return
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
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
  if (polling.value) {
    timer = setTimeout(() => void pollStatus(), 2500)
  }
}

function beginPolling(): void {
  stopPolling()
  timedOut.value = false
  polling.value = true
  pollStartedAt = Date.now()
  void pollStatus()
}

async function startCollect(refresh = false): Promise<void> {
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
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

watch(() => props.code, () => {
  stopPolling()
  task.value = null
  data.value = null
  error.value = ''
  timedOut.value = false
  void startCollect(false)
})

onMounted(() => void startCollect(false))
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="card full-data-panel">
    <div class="data-panel-header">
      <div>
        <div class="data-panel-title">全维度数据</div>
        <div class="data-panel-subtitle">零 token · 十二章完整原始数据</div>
      </div>
      <button v-if="data" class="btn btn-ghost" @click="startCollect(true)">重新采集</button>
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
      <div class="data-status-bar">
        <span :class="['data-status-badge', data.cached ? 'is-cached' : 'is-live']">
          {{ data.cached ? '当日缓存' : '实时采集' }}
        </span>
        <span>采集时间 {{ data.fetched_at }}</span>
        <span>共 {{ chapters.length }} 个章节</span>
      </div>

      <!-- 数据源异常默认收起，避免技术错误占据主视觉 -->
      <details v-if="sourceErrors.length" class="source-warning">
        <summary>
          <span>部分数据暂不可用（{{ sourceErrors.length }} 项），其余章节不受影响</span>
          <span class="source-warning-action">查看技术详情</span>
        </summary>
        <div class="source-error-list">
          <div v-for="[source, message] in sourceErrors" :key="source" class="source-error-item">
            <strong>{{ source }}</strong>
            <span>{{ message }}</span>
          </div>
        </div>
      </details>

      <div class="data-workbench">
        <aside class="data-sidebar">
          <div class="data-sidebar-title">章节目录</div>
          <nav class="data-chapter-nav" aria-label="数据目录">
            <a v-for="chapter in chapters" :key="chapter.key" :href="`#data-${chapter.key}`">
              <span class="data-nav-dot"></span>
              {{ chapter.title }}
            </a>
          </nav>
        </aside>

        <article class="report-body data-content">
          <section
            v-for="chapter in chapters"
            :id="`data-${chapter.key}`"
            :key="chapter.key"
            class="chapter-section data-chapter"
          >
            <h2>{{ chapter.title }}</h2>
            <details :open="!COLLAPSED_BY_DEFAULT.has(chapter.key)">
              <summary>查看本章全部数据</summary>
              <div class="data-table-wrap" v-html="renderMarkdown(chapter.data_md)"></div>
            </details>
          </section>
        </article>
      </div>
    </template>
  </section>
</template>
