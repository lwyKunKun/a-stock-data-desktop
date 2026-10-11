<!--
  ReportList.vue —— 已生成报告列表
  数据源为后端 SQLite 索引（backend/data/reports_index.db），首次查询自动回填历史报告。
  支持按日期、行业筛选；点击行跳转回该股票的查询页。
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchReportList } from '../api/client'
import type { ReportListItem, ReportListResponse } from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

const emit = defineEmits<{ select: [code: string] }>()

const data = ref<ReportListResponse | null>(null)
const filterDate = ref<string>('')
const filterIndustry = ref<string>('')
const loading = ref<boolean>(false)
const error = ref<string>('')
let controller: AbortController | null = null

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  controller?.abort()
  controller = new AbortController()
  try {
    data.value = await fetchReportList(filterDate.value, filterIndustry.value, controller.signal)
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught)
  } finally {
    loading.value = false
  }
}

function select(item: ReportListItem): void {
  emit('select', item.code)
}

function changePctClass(value: number | null): string {
  if (value === null || value === undefined) return ''
  return value >= 0 ? 'is-up' : 'is-down'
}

function formatPct(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <section class="card report-list">
    <div class="report-list-head">
      <div>
        <div class="card-title">已生成报告</div>
        <p class="muted report-list-subtitle">SQLite 索引 · 点击行查看该股票当日报告</p>
      </div>
      <button class="btn btn-ghost" :disabled="loading" @click="load">刷新</button>
    </div>

    <div class="report-list-filters">
      <label>
        日期
        <select v-model="filterDate" class="input" @change="load">
          <option value="">全部日期</option>
          <option v-for="date in data?.dates ?? []" :key="date" :value="date">{{ date }}</option>
        </select>
      </label>
      <label>
        行业
        <select v-model="filterIndustry" class="input" @change="load">
          <option value="">全部行业</option>
          <option v-for="industry in data?.industries ?? []" :key="industry" :value="industry">
            {{ industry }}
          </option>
        </select>
      </label>
      <span v-if="data" class="muted">共 {{ data.items.length }} 份</span>
    </div>

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="data && !data.items.length && !loading" class="muted report-list-empty">
      暂无符合条件的报告，先在上方搜索股票生成一份
    </div>

    <table v-if="data && data.items.length" class="report-list-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>股票</th>
          <th>行业</th>
          <th>现价</th>
          <th>涨跌幅</th>
          <th>PE(TTM)</th>
          <th>模型</th>
          <th>Tokens</th>
          <th>耗时</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in data.items" :key="`${item.date}-${item.code}`" @click="select(item)">
          <td class="muted">{{ item.date }}</td>
          <td>
            <strong>{{ item.name || item.code }}</strong>
            <span class="muted"> {{ item.code }}</span>
          </td>
          <td>{{ item.industry || '—' }}</td>
          <td>{{ item.price ?? '—' }}</td>
          <td :class="changePctClass(item.change_pct)">{{ formatPct(item.change_pct) }}</td>
          <td>{{ item.pe_ttm ?? '—' }}</td>
          <td class="muted">{{ item.model }}</td>
          <td class="muted">{{ item.total_tokens }}</td>
          <td class="muted">{{ item.duration_s }}s</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.report-list {
  margin-top: 14px;
  padding: 16px 20px;
}
.report-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.report-list-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
}
.report-list-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin: 12px 0;
  font-size: 12px;
  color: var(--text-light);
}
.report-list-filters label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.report-list-filters select {
  width: auto;
  padding: 4px 8px;
  font-size: 12px;
}
.report-list-empty {
  padding: 18px 0;
  text-align: center;
}
.report-list-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.report-list-table th,
.report-list-table td {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}
.report-list-table th {
  color: var(--text-light);
  font-size: 12px;
  font-weight: 500;
  border-top: none;
}
.report-list-table tbody tr {
  cursor: pointer;
}
.report-list-table tbody tr:hover {
  background: #f8efee;
}
.is-up { color: var(--up); }
.is-down { color: var(--down); }
</style>
