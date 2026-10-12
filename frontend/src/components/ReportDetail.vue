<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchReport, fetchReportStatus, retryReportChapter } from '../api/client'
import type { FullReport } from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'
import ReportViewer from './ReportViewer.vue'

interface Props {
  code: string
  date: string
  name?: string
}

const props = withDefaults(defineProps<Props>(), { name: '' })
const emit = defineEmits<{ back: [] }>()

const report = ref<FullReport | null>(null)
const loading = ref<boolean>(false)
const error = ref<string>('')
const retryingKey = ref<string>('')
let controller: AbortController | null = null

// 后端章节重试只作用于当天报告文件，历史归档保持只读
const isToday = computed<boolean>(() => props.date === localDate())

function localDate(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

async function load(): Promise<void> {
  controller?.abort()
  const requestController = new AbortController()
  controller = requestController
  report.value = null
  error.value = ''
  loading.value = true
  try {
    const loaded = await fetchReport(props.code, props.date, requestController.signal)
    if (controller !== requestController) return
    report.value = loaded
  } catch (caught: unknown) {
    if (controller === requestController && !isAbortError(caught)) {
      error.value = errorMessage(caught)
    }
  } finally {
    if (controller === requestController) {
      controller = null
      loading.value = false
    }
  }
}

async function retryChapter(key: string): Promise<void> {
  if (!isToday.value || retryingKey.value) return
  error.value = ''
  retryingKey.value = key
  const requestController = new AbortController()
  controller = requestController
  try {
    await retryReportChapter(props.code, key, requestController.signal)
    // 轮询后端任务直至结束，再重新读取当天报告展示重试结果
    const startedAt = Date.now()
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 2500))
      if (controller !== requestController) return
      if (Date.now() - startedAt > 10 * 60 * 1000) {
        error.value = '重试等待超时，请点击“重新加载”查看最新结果'
        return
      }
      const status = await fetchReportStatus(props.code, requestController.signal)
      if (['done', 'done_with_warnings', 'failed'].includes(status.status)) break
    }
    if (controller !== requestController) return
    await load()
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  } finally {
    if (controller === requestController) controller = null
    retryingKey.value = ''
  }
}

watch(
  () => [props.code, props.date],
  () => void load(),
  { immediate: true },
)

onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="report-detail">
    <header class="report-detail-head">
      <button type="button" class="btn btn-ghost" @click="emit('back')">返回报告列表</button>
      <div>
        <h1>{{ name || report?.name || code }} <span class="muted">{{ code }}</span></h1>
        <p class="muted">归档日期：{{ date }}</p>
      </div>
    </header>

    <div v-if="loading" class="card loading">
      <span class="spinner"></span>正在加载 {{ date }} 的完整报告…
    </div>

    <div v-else-if="error" class="card report-detail-state">
      <div class="error-box">{{ error }}</div>
      <button type="button" class="btn btn-ghost" @click="load">重新加载</button>
    </div>

    <div v-else-if="!report" class="card report-detail-state">
      <p>未找到 {{ code }} 在 {{ date }} 生成的报告。</p>
      <p class="muted">该归档文件可能已被删除，请返回列表刷新索引。</p>
    </div>

    <div v-else class="card report-detail-card">
      <ReportViewer
        :report="report"
        cache-label="历史归档"
        :id-prefix="`archive-${date}-${code}`"
        :allow-retry="isToday"
        @retry="retryChapter"
      />
    </div>
  </section>
</template>
