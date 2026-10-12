<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import type { ChapterState, FullReport, ReportChapter } from '../api/types'

interface Props {
  report: FullReport
  cacheLabel?: string
  allowRetry?: boolean
  idPrefix?: string
}

const props = withDefaults(defineProps<Props>(), {
  cacheLabel: '完整报告',
  allowRetry: false,
  idPrefix: 'report',
})
const emit = defineEmits<{ retry: [chapterKey: string] }>()

const summaryChapter = computed<ReportChapter | null>(
  () => props.report.chapters.find((item) => item.key === 'ch10_summary') ?? null,
)
const regularChapters = computed<ReportChapter[]>(
  () => props.report.chapters.filter((item) => item.key !== 'ch10_summary'),
)

function renderMarkdown(value: string): string {
  const html = marked.parse(value || '', { async: false })
  if (typeof html !== 'string') throw new Error('Markdown 渲染器返回了异步结果')
  return DOMPurify.sanitize(html)
}

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

const legacyDataWarning = /\n{2,}>\s*部分数据源未获取：([\s\S]+?)\s*$/

function chapterDataMarkdown(chapter: ReportChapter): string {
  const markdown = chapter.data_md || ''
  if (chapter.data_warnings?.length) return markdown
  return markdown.replace(legacyDataWarning, '').trim()
}

function chapterWarnings(chapter: ReportChapter): string[] {
  const warnings = (chapter.data_warnings ?? []).map((item) => item.trim()).filter(Boolean)
  if (warnings.length) return warnings
  const legacy = (chapter.data_md || '').match(legacyDataWarning)?.[1]?.trim()
  return legacy ? [legacy] : []
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

function canRetry(chapter: ReportChapter): boolean {
  return props.allowRetry && ['comment_failed', 'data_failed'].includes(chapter.state)
}

function chapterId(key: string): string {
  return `${props.idPrefix}-${key}`
}
</script>

<template>
  <div class="report-viewer">
    <div class="report-meta">
      <span class="tag">{{ cacheLabel }}</span>
      <span class="muted">{{ report.meta?.generated_at }}</span>
      <span v-if="report.meta?.model" class="muted">{{ report.meta.model }}</span>
      <span v-if="report.meta?.usage" class="muted">
        tokens: {{ report.meta.usage.total_tokens || 0 }}
      </span>
      <span v-if="report.meta?.duration_s" class="muted">耗时: {{ report.meta.duration_s }}s</span>
      <slot name="actions"></slot>
    </div>

    <div v-if="!report.chapters.length" class="muted report-viewer-empty">
      该归档报告没有可展示的章节
    </div>

    <div v-else class="data-workbench ai-workbench">
      <aside class="data-sidebar">
        <div class="data-sidebar-title">报告目录</div>
        <nav class="data-chapter-nav" aria-label="报告目录">
          <a
            v-for="chapter in report.chapters"
            :key="chapter.key"
            :class="{ 'is-summary': chapter.key === 'ch10_summary' }"
            :href="`#${chapterId(chapter.key)}`"
          >
            <span class="data-nav-dot"></span>
            {{ chapter.title }}
          </a>
        </nav>
      </aside>

      <div class="data-content ai-report-content">
        <section v-if="summaryChapter" :id="chapterId(summaryChapter.key)" class="summary-card">
          <div class="summary-head">
            <h2>{{ summaryChapter.title }}</h2>
            <span v-if="summaryChapter.state !== 'ok'" class="tag">
              {{ chapterStateLabel(summaryChapter) }}
            </span>
          </div>
          <div
            v-if="chapterComment(summaryChapter)"
            class="chapter-comment"
            v-html="renderMarkdown(chapterComment(summaryChapter))"
          ></div>
          <details v-if="chapterDataMarkdown(summaryChapter)" class="chapter-data">
            <summary>查看估值情景表等数据</summary>
            <div v-html="renderMarkdown(chapterDataMarkdown(summaryChapter))"></div>
          </details>
          <details v-if="chapterWarnings(summaryChapter).length" class="chapter-source-warning">
            <summary>
              <span>
                部分数据源暂不可用（{{ chapterWarnings(summaryChapter).length }} 项），其余数据不受影响
              </span>
              <span class="chapter-warning-action">查看技术详情</span>
            </summary>
            <div class="chapter-warning-details">
              <div
                v-for="(detail, index) in chapterWarnings(summaryChapter)"
                :key="index"
                class="chapter-warning-detail"
              >{{ detail }}</div>
            </div>
          </details>
          <button
            v-if="canRetry(summaryChapter)"
            class="btn btn-ghost chapter-retry"
            @click="emit('retry', summaryChapter.key)"
          >重试综合评估</button>
        </section>

        <article class="report-body">
          <section
            v-for="chapter in regularChapters"
            :id="chapterId(chapter.key)"
            :key="chapter.key"
            class="chapter-section"
          >
            <h2>{{ chapter.title }}</h2>
            <div
              v-if="chapterComment(chapter)"
              class="chapter-comment"
              v-html="renderMarkdown(chapterComment(chapter))"
            ></div>
            <details
              v-if="chapterDataMarkdown(chapter)"
              class="chapter-data"
              :open="['ch4_finance', 'ch5_chips'].includes(chapter.key)"
            >
              <summary>查看本章数据表格</summary>
              <div v-html="renderMarkdown(chapterDataMarkdown(chapter))"></div>
            </details>
            <details v-if="chapterWarnings(chapter).length" class="chapter-source-warning">
              <summary>
                <span>
                  部分数据源暂不可用（{{ chapterWarnings(chapter).length }} 项），其余数据不受影响
                </span>
                <span class="chapter-warning-action">查看技术详情</span>
              </summary>
              <div class="chapter-warning-details">
                <div
                  v-for="(detail, index) in chapterWarnings(chapter)"
                  :key="index"
                  class="chapter-warning-detail"
                >{{ detail }}</div>
              </div>
            </details>
            <button
              v-if="canRetry(chapter)"
              class="btn btn-ghost chapter-retry"
              @click="emit('retry', chapter.key)"
            >重试本章点评</button>
          </section>
        </article>
      </div>
    </div>
  </div>
</template>
