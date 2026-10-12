<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchReport } from '../api/client'
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
let controller: AbortController | null = null

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
      />
    </div>
  </section>
</template>
