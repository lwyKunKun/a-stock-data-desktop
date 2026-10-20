<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchMarketReport,
  fetchMarketReportStatus,
  generateMarketReport,
  retryMarketReportChapter,
} from '../api/client'
import type {
  ChapterState,
  FullReport,
  Market,
  Progress,
  ReportChapter,
  ReportTaskStatus,
} from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'
import { getRuntimeSource } from '../utils/runtime'

interface Props {
  code: string
  name?: string
  market?: Market
}

const props = withDefaults(defineProps<Props>(), { name: '', market: 'CN' })
const emit = defineEmits<{
  generated: [report: { code: string; date: string; market: Market }]
  view: [report: { code: string; date: string; market: Market }]
}>()

const task = ref<ReportTaskStatus | null>(null)
const report = ref<FullReport | null>(null)
const error = ref<string>('')
const polling = ref<boolean>(false)
const timedOut = ref<boolean>(false)
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null
let pollStartedAt = 0
let generationRequested = false
let completionEmitted = false

const chapters = computed<ReportChapter[]>(
  () => report.value?.chapters ?? task.value?.chapters ?? [],
)
const progress = computed<Progress>(
  () => task.value?.progress ?? { done: report.value ? (report.value.chapters.length || 1) : 0, total: report.value?.chapters.length || 1 },
)
const progressPct = computed<number>(() => {
  const total = progress.value.total || 1
  return Math.min(100, Math.round((progress.value.done || 0) / total * 100))
})

const failedChapters = computed<ReportChapter[]>(() =>
  (report.value?.chapters ?? []).filter((chapter) => canRetry(chapter)),
)

function chapterState(chapter: ReportChapter): ChapterState {
  return chapter.state || 'pending'
}

const chapterLabels: Record<ChapterState, string> = {
  pending: '待处理',
  fetching: '取数中',
  data_ok: '数据完成',
  data_failed: '数据失败',
  generating: '生成中',
  ok: '完成',
  comment_failed: '点评失败',
}

function chapterStateLabel(chapter: ReportChapter): string {
  return chapterLabels[chapterState(chapter)]
}

function canRetry(chapter: ReportChapter): boolean {
  return ['comment_failed', 'data_failed'].includes(chapter.state)
}

function localDate(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function reportDate(value: FullReport): string {
  const date = String(value.meta?.generated_at ?? '').slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : localDate()
}

function stopPolling(): void {
  if (timer) clearTimeout(timer)
  timer = null
  polling.value = false
  controller?.abort()
  controller = null
}

async function loadReport(): Promise<void> {
  controller = new AbortController()
  const loaded = await fetchMarketReport(props.market, props.code, undefined, controller.signal)
  if (!loaded) throw new Error('报告任务已完成，但未找到生成结果')
  report.value = loaded
  task.value = {
    ...(task.value ?? {}),
    status: 'done',
    progress: { done: loaded.chapters.length, total: loaded.chapters.length },
  }
  if (generationRequested && !completionEmitted) {
    completionEmitted = true
    generationRequested = false
    emit('generated', { code: props.code, date: reportDate(loaded), market: props.market })
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
    const status = await fetchMarketReportStatus(props.market, props.code, controller.signal)
    task.value = status
    if (status.status === 'done' || status.status === 'done_with_warnings') {
      polling.value = false
      await loadReport()
      return
    }
    if (status.status === 'failed') {
      polling.value = false
      generationRequested = false
      error.value = status.error || '报告任务失败'
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

async function startGeneration(refresh = false): Promise<void> {
  if (refresh && !window.confirm('重新生成会再次调用 AI 并产生 token 费用，确定继续吗？')) return
  stopPolling()
  error.value = ''
  timedOut.value = false
  generationRequested = true
  completionEmitted = false
  if (refresh) report.value = null
  try {
    controller = new AbortController()
    const result = await generateMarketReport(
      props.market,
      props.code,
      refresh,
      getRuntimeSource(),
      controller.signal,
    )
    task.value = result
    if (result.status === 'done' && result.cached) {
      await loadReport()
    } else {
      beginPolling()
    }
  } catch (caught: unknown) {
    generationRequested = false
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

async function retryChapter(key: string): Promise<void> {
  error.value = ''
  try {
    controller = new AbortController()
    task.value = await retryMarketReportChapter(props.market, props.code, key, controller.signal)
    beginPolling()
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

// 完整报告统一在「已生成的报告」归档详情中查看，看板这里只负责跳转
function viewReport(): void {
  if (!report.value) return
  emit('view', { code: props.code, date: reportDate(report.value), market: props.market })
}

async function initialize(): Promise<void> {
  error.value = ''
  try {
    controller = new AbortController()
    const existing = await fetchMarketReport(props.market, props.code, undefined, controller.signal)
    if (existing) {
      report.value = existing
      task.value = { status: 'done', progress: { done: existing.chapters.length, total: existing.chapters.length } }
    }
  } catch (caught: unknown) {
    if (isAbortError(caught)) return
    error.value = errorMessage(caught)
  }
}

watch(() => [props.code, props.market], () => {
  stopPolling()
  task.value = null
  report.value = null
  error.value = ''
  timedOut.value = false
  generationRequested = false
  completionEmitted = false
  void initialize()
})

onMounted(() => void initialize())
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="card ai-report">
    <div class="ai-report-head">
      <div class="report-title-row">
        <div class="card-title">AI 全维度分析</div>
      </div>

      <p class="muted report-hint">
        手动生成，避免意外产生 AI token 费用；当日已生成的报告会直接读取缓存
      </p>

      <button v-if="!report && !polling && !task" class="btn btn-ai" @click="startGeneration(false)">
        生成全维度报告
      </button>

      <div v-if="task && !report" class="report-progress">
        <div class="progress-heading">
          <span>{{ task.status === 'aggregating' ? '正在聚合数据' : '正在分章生成报告' }}</span>
          <strong>{{ progressPct }}%</strong>
        </div>
        <div class="progress-track"><span :style="{ width: `${progressPct}%` }"></span></div>
        <p v-if="task.current_chapter" class="muted">当前章节：{{ task.current_chapter }}</p>
        <div class="chapter-status-list">
          <a
            v-for="chapter in chapters"
            :key="chapter.key"
            :class="['chapter-chip', `is-${chapterState(chapter)}`]"
          >{{ chapter.title }} · {{ chapterStateLabel(chapter) }}</a>
        </div>
      </div>
    </div>

    <!-- 今日报告已生成：看板只显示摘要卡片，完整报告去归档详情查看 -->
    <div v-if="report" class="report-progress ai-report-done">
      <div class="progress-heading">
        <span>今日报告已生成</span>
        <span class="muted">{{ report.meta?.generated_at }}</span>
      </div>
      <div class="chapter-status-list">
        <a
          v-for="chapter in report.chapters"
          :key="chapter.key"
          :class="['chapter-chip', `is-${chapterState(chapter)}`, { clickable: canRetry(chapter) }]"
          :title="canRetry(chapter) ? '点击重试本章' : chapterStateLabel(chapter)"
          @click="canRetry(chapter) && retryChapter(chapter.key)"
        >{{ chapter.title }} · {{ chapterStateLabel(chapter) }}</a>
      </div>
      <p v-if="failedChapters.length" class="muted">
        点击“数据失败 / 点评失败”的章节可单独重试，其余章节不受影响
      </p>
      <div class="ai-report-done-actions">
        <button class="btn btn-primary" @click="viewReport">查看完整报告</button>
        <button class="btn btn-ghost" @click="startGeneration(true)">重新生成</button>
      </div>
    </div>

    <div v-if="timedOut" class="warning-box">
      前端已停止等待，但后端任务仍会继续。点击“继续查看进度”恢复轮询。
      <button class="btn btn-ghost" @click="beginPolling">继续查看进度</button>
    </div>
    <div v-if="error" class="error-box">{{ error }}</div>
  </section>
</template>
