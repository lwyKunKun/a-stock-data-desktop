<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  fetchReport,
  fetchReportStatus,
  generateReport,
  retryReportChapter,
} from '../api/client'
import type {
  ChapterState,
  FullReport,
  Progress,
  ReportChapter,
  ReportTaskStatus,
} from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

interface Props {
  code: string
  name?: string
}

const props = withDefaults(defineProps<Props>(), { name: '' })

// 触发方式已固定为全程手动：只有用户点击按钮才会调用 AI 产生 token 费用
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
const summaryChapter = computed<ReportChapter | null>(
  () => report.value?.chapters.find((item) => item.key === 'ch10_summary') ?? null,
)
const regularChapters = computed<ReportChapter[]>(
  () => report.value?.chapters.filter((item) => item.key !== 'ch10_summary') ?? [],
)
const progress = computed<Progress>(
  () => task.value?.progress ?? { done: report.value ? 12 : 0, total: 12 },
)
const progressPct = computed<number>(() => {
  const total = progress.value.total || 12
  return Math.min(100, Math.round((progress.value.done || 0) / total * 100))
})

function renderMarkdown(value: string): string {
  const html = marked.parse(value || '', { async: false })
  if (typeof html !== 'string') throw new Error('Markdown 渲染器返回了异步结果')
  return DOMPurify.sanitize(html)
}

// 旧版提示词会让 AI 在正文开头重复输出「## 十、综合评估」这类章节标题，
// 渲染前剥掉，避免与章节自身的 <h2> 重复（新报告后端已不存，这里兼容当日旧缓存）
function stripEchoedHeading(md: string, title: string): string {
  const lines = (md || '').split('\n')
  while (lines.length && !lines[0].trim()) lines.shift()
  const match = lines[0]?.match(/^#{1,3}\s+(.+?)\s*$/)
  if (match && match[1].replace(/[《》\s]/g, '') === title.replace(/[《》\s]/g, '')) {
    lines.shift()
  }
  return lines.join('\n').trim()
}

function chapterComment(chapter: ReportChapter): string {
  return stripEchoedHeading(chapter.comment_md || '', chapter.title)
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
    status: 'done',
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
            :href="report ? `#${chapter.key}` : undefined"
          >{{ chapter.title }} · {{ chapterStateLabel(chapter) }}</a>
        </div>
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

      <!-- 左右工作台：左侧章节目录侧边栏，右侧报告内容（复用 data-workbench 布局与样式） -->
      <div class="data-workbench ai-workbench">
        <aside class="data-sidebar">
          <div class="data-sidebar-title">报告目录</div>
          <nav class="data-chapter-nav" aria-label="报告目录">
            <a
              v-for="chapter in report.chapters"
              :key="chapter.key"
              :class="{ 'is-summary': chapter.key === 'ch10_summary' }"
              :href="`#${chapter.key}`"
            >
              <span class="data-nav-dot"></span>
              {{ chapter.title }}
            </a>
          </nav>
        </aside>

        <div class="data-content ai-report-content">
          <section v-if="summaryChapter" :id="summaryChapter.key" class="summary-card">
            <div class="summary-head">
              <h2>{{ summaryChapter.title }}</h2>
              <span v-if="summaryChapter.state !== 'ok'" class="tag">{{ chapterStateLabel(summaryChapter) }}</span>
            </div>
            <div class="chapter-comment" v-html="renderMarkdown(chapterComment(summaryChapter))"></div>
            <details v-if="summaryChapter.data_md" class="chapter-data">
              <summary>查看估值情景表等数据</summary>
              <div v-html="renderMarkdown(summaryChapter.data_md)"></div>
            </details>
            <button
              v-if="['comment_failed', 'data_failed'].includes(summaryChapter.state)"
              class="btn btn-ghost chapter-retry"
              @click="retryChapter(summaryChapter.key)"
            >重试综合评估</button>
          </section>

          <article class="report-body">
            <section
              v-for="chapter in regularChapters"
              :id="chapter.key"
              :key="chapter.key"
              class="chapter-section"
            >
              <h2>{{ chapter.title }}</h2>
              <div
                v-if="chapterComment(chapter)"
                class="chapter-comment"
                v-html="renderMarkdown(chapterComment(chapter))"
              ></div>
              <details v-if="chapter.data_md" class="chapter-data" :open="['ch4_finance', 'ch5_chips'].includes(chapter.key)">
                <summary>查看本章数据表格</summary>
                <div v-html="renderMarkdown(chapter.data_md)"></div>
              </details>
              <button
                v-if="['comment_failed', 'data_failed'].includes(chapter.state)"
                class="btn btn-ghost chapter-retry"
                @click="retryChapter(chapter.key)"
              >重试本章点评</button>
            </section>
          </article>
        </div>
      </div>
    </template>
  </section>
</template>
