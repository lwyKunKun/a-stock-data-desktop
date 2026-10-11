<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  fetchReport,
  fetchReportConfig,
  fetchReportStatus,
  generateReport,
  retryReportChapter,
  retryReportPublish,
} from '../api/client'
import type {
  ChapterState,
  FullReport,
  Progress,
  Publication,
  ReportChapter,
  ReportTaskStatus,
} from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

interface Props {
  code: string
  name?: string
}

type TriggerMode = 'manual' | 'auto'

const props = withDefaults(defineProps<Props>(), { name: '' })

function storedTriggerMode(): TriggerMode {
  return localStorage.getItem('ai_trigger_mode') === 'auto' ? 'auto' : 'manual'
}

const triggerMode = ref<TriggerMode>(storedTriggerMode())
const task = ref<ReportTaskStatus | null>(null)
const report = ref<FullReport | null>(null)
const error = ref<string>('')
const polling = ref<boolean>(false)
const timedOut = ref<boolean>(false)
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null
let pollStartedAt = 0

const chapters = computed<ReportChapter[]>(
  () => report.value?.chapters ?? task.value?.chapters ?? [],
)
const progress = computed<Progress>(
  () => task.value?.progress ?? { done: report.value ? 12 : 0, total: 12 },
)
const progressPct = computed<number>(() => {
  const total = progress.value.total || 12
  return Math.min(100, Math.round((progress.value.done || 0) / total * 100))
})
const publication = computed<Publication>(() => report.value?.meta.publication ?? {})
const publicationFailed = computed<boolean>(
  () => Boolean(report.value && publication.value.ok === false),
)

function renderMarkdown(value: string): string {
  const html = marked.parse(value || '', { async: false })
  if (typeof html !== 'string') throw new Error('Markdown 渲染器返回了异步结果')
  return DOMPurify.sanitize(html)
}

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

function stopPolling(): void {
  if (timer) clearTimeout(timer)
  timer = null
  polling.value = false
  controller?.abort()
  controller = null
}

async function loadReport(): Promise<void> {
  controller = new AbortController()
  const loaded = await fetchReport(props.code, controller.signal)
  if (!loaded) throw new Error('报告任务已完成，但未找到生成结果')
  report.value = loaded
  task.value = {
    ...(task.value ?? {}),
    status: loaded.meta.publication?.ok === false ? 'done_with_warnings' : 'done',
    progress: { done: 12, total: 12 },
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
    const status = await fetchReportStatus(props.code, controller.signal)
    task.value = status
    if (status.status === 'done' || status.status === 'done_with_warnings') {
      polling.value = false
      await loadReport()
      return
    }
    if (status.status === 'failed') {
      polling.value = false
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
  if (refresh) report.value = null
  try {
    controller = new AbortController()
    const result = await generateReport(props.code, refresh, controller.signal)
    task.value = result
    if (result.status === 'done' && result.cached) {
      await loadReport()
    } else {
      beginPolling()
    }
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

async function retryChapter(key: string): Promise<void> {
  error.value = ''
  try {
    controller = new AbortController()
    task.value = await retryReportChapter(props.code, key, controller.signal)
    beginPolling()
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

async function retryPublish(): Promise<void> {
  error.value = ''
  try {
    controller = new AbortController()
    task.value = await retryReportPublish(props.code, controller.signal)
    beginPolling()
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  }
}

function setMode(mode: TriggerMode): void {
  triggerMode.value = mode
  localStorage.setItem('ai_trigger_mode', mode)
  if (mode === 'auto' && !report.value && !polling.value) void startGeneration(false)
}

async function initialize(): Promise<void> {
  error.value = ''
  try {
    controller = new AbortController()
    const existing = await fetchReport(props.code, controller.signal)
    if (existing) {
      report.value = existing
      task.value = { status: 'done', progress: { done: 12, total: 12 } }
      return
    }
  } catch (caught: unknown) {
    if (isAbortError(caught)) return
    error.value = errorMessage(caught)
    return
  }
  if (!localStorage.getItem('ai_trigger_mode')) {
    try {
      controller = new AbortController()
      const config = await fetchReportConfig(controller.signal)
      triggerMode.value = config.auto_trigger_default ? 'auto' : 'manual'
    } catch {
      triggerMode.value = 'manual'
    }
  }
  if (triggerMode.value === 'auto') void startGeneration(false)
}

watch(() => props.code, () => {
  stopPolling()
  task.value = null
  report.value = null
  error.value = ''
  timedOut.value = false
  void initialize()
})

onMounted(() => void initialize())
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="card ai-report">
    <div class="report-title-row">
      <div class="card-title">AI 全维度分析</div>
      <div class="trigger-switch" role="group" aria-label="报告触发模式">
        <button :class="{ active: triggerMode === 'manual' }" @click="setMode('manual')">手动</button>
        <button :class="{ active: triggerMode === 'auto' }" @click="setMode('auto')">自动</button>
      </div>
    </div>

    <p class="muted report-hint">
      {{ triggerMode === 'auto' ? '进入个股详情后自动生成或读取当日缓存' : '手动生成，避免意外产生 AI token 费用' }}
    </p>

    <button v-if="!report && !polling && !task" class="btn btn-ai" @click="startGeneration(false)">
      生成全维度报告
    </button>

    <div v-if="task && !report" class="report-progress">
      <div class="progress-heading">
        <span>{{ task.status === 'aggregating' ? '正在聚合数据' : task.status === 'publishing' ? '正在发布报告' : '正在分章生成报告' }}</span>
        <strong>{{ progressPct }}%</strong>
      </div>
      <div class="progress-track"><span :style="{ width: `${progressPct}%` }"></span></div>
      <p v-if="task.current_chapter" class="muted">当前章节：{{ task.current_chapter }}</p>
      <div class="chapter-status-list">
        <a
          v-for="chapter in chapters"
          :key="chapter.key"
          :class="['chapter-chip', `is-${chapterState(chapter)}`]"
          :href="report ? `#${chapter.key}` : undefined"
        >{{ chapter.title }} · {{ chapterStateLabel(chapter) }}</a>
      </div>
    </div>

    <div v-if="timedOut" class="warning-box">
      前端已停止等待，但后端任务仍会继续。点击“继续查看进度”恢复轮询。
      <button class="btn btn-ghost" @click="beginPolling">继续查看进度</button>
    </div>
    <div v-if="error" class="error-box">{{ error }}</div>

    <template v-if="report">
      <div class="report-meta">
        <span class="tag">{{ task?.cached ? '当日缓存' : '完整报告' }}</span>
        <span class="muted">{{ report.meta?.generated_at }}</span>
        <span v-if="report.meta?.model" class="muted">{{ report.meta.model }}</span>
        <span v-if="report.meta?.usage" class="muted">tokens: {{ report.meta.usage.total_tokens || 0 }}</span>
        <span v-if="report.meta?.duration_s" class="muted">耗时: {{ report.meta.duration_s }}s</span>
        <button class="btn btn-ghost report-refresh" @click="startGeneration(true)">重新生成</button>
      </div>

      <div v-if="publicationFailed" class="warning-box">
        报告已生成，但发布未全部完成：{{ publication.error || '请查看发布阶段状态' }}
        <button class="btn btn-ghost" @click="retryPublish">重试发布</button>
      </div>
      <div v-else-if="publication.ok" class="success-box">
        已写入 Obsidian{{ publication.obsidian?.category ? `（${publication.obsidian.category}）` : '' }}，并完成同步发布。
      </div>

      <nav class="chapter-nav" aria-label="报告目录">
        <a v-for="chapter in report.chapters" :key="chapter.key" :href="`#${chapter.key}`">
          {{ chapter.title }}
        </a>
      </nav>

      <article class="report-body">
        <section
          v-for="chapter in report.chapters"
          :id="chapter.key"
          :key="chapter.key"
          class="chapter-section"
        >
          <h2>{{ chapter.title }}</h2>
          <details :open="!['ch4_finance', 'ch5_chips'].includes(chapter.key)">
            <summary>查看本章数据与点评</summary>
            <div v-html="renderMarkdown(`${chapter.data_md || ''}\n\n${chapter.comment_md || ''}`)"></div>
          </details>
          <button
            v-if="['comment_failed', 'data_failed'].includes(chapter.state)"
            class="btn btn-ghost chapter-retry"
            @click="retryChapter(chapter.key)"
          >重试本章点评</button>
        </section>
      </article>
    </template>
  </section>
</template>
