<!--
  DataSourceBanner.vue —— 数据源仓库更新提醒
  轮询后端 /api/datasource/status（服务端有 10 分钟缓存，不会触发 GitHub 限流），
  上游 simonlin1212/a-stock-data 有新提交且用户未确认时，在页面顶部显示横幅。
  「生成更新报告」按钮：调用 compare API 生成「已确认版本 → 最新版本」的
  函数级差异报告，并映射到后端移植文件，展开显示在横幅下方。
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ackDatasourceUpdate,
  fetchDatasourceReport,
  fetchDatasourceStatus,
} from '../api/client'
import type { DatasourceCommit, DatasourceReport, DatasourceStatus } from '../api/types'
import { errorMessage } from '../utils/errors'

const visible = ref<boolean>(false)
const commitsUrl = ref<string>('https://github.com/simonlin1212/a-stock-data/commits')
const latest = ref<DatasourceCommit | null>(null)
const report = ref<DatasourceReport | null>(null)
const reportLoading = ref<boolean>(false)
const reportError = ref<string>('')
let timer: ReturnType<typeof setTimeout> | null = null
const POLL_INTERVAL = 10 * 60 * 1000 // 与后端缓存周期一致

function stopPolling(): void {
  if (timer) clearTimeout(timer)
  timer = null
}

async function check(): Promise<void> {
  try {
    const status: DatasourceStatus = await fetchDatasourceStatus()
    commitsUrl.value = status.commits_url
    latest.value = status.latest
    visible.value = status.update_available
  } catch {
    // 检查失败不打断用户，下一轮再试
  }
  timer = setTimeout(() => void check(), POLL_INTERVAL)
}

async function loadReport(): Promise<void> {
  // 再次点击已展开的报告时收起
  if (report.value && !reportLoading.value) {
    report.value = null
    return
  }
  reportLoading.value = true
  reportError.value = ''
  try {
    report.value = await fetchDatasourceReport()
  } catch (caught: unknown) {
    reportError.value = errorMessage(caught)
  } finally {
    reportLoading.value = false
  }
}

async function dismiss(): Promise<void> {
  visible.value = false
  stopPolling()
  try {
    await ackDatasourceUpdate()
  } catch (caught: unknown) {
    // 确认失败时下次刷新会重新提示，无需打扰用户
    console.warn('确认数据源更新失败：', errorMessage(caught))
  }
}

function shortSha(sha: string): string {
  return sha ? sha.slice(0, 7) : ''
}

const FILE_STATUS_LABELS: Record<string, string> = {
  added: '新增',
  modified: '修改',
  removed: '删除',
  renamed: '重命名',
}

function fileStatusLabel(status: string): string {
  return FILE_STATUS_LABELS[status] ?? status
}

onMounted(() => void check())
onBeforeUnmount(stopPolling)
</script>

<template>
  <div v-if="visible">
    <div class="datasource-banner">
      <span>
        📦 数据源仓库有新提交
        <template v-if="latest">
          ：{{ latest.message }}
          <span class="muted" v-if="latest.author">（{{ latest.author }}）</span>
        </template>
        ，建议同步更新数据源。
        <a :href="commitsUrl" target="_blank" rel="noopener">查看更新内容</a>
      </span>
      <span class="banner-actions">
        <button class="btn btn-ghost" :disabled="reportLoading" @click="loadReport">
          {{ reportLoading ? '生成中…' : report ? '收起报告' : '生成更新报告' }}
        </button>
        <button class="btn btn-ghost" @click="dismiss">知道了</button>
      </span>
    </div>

    <!-- 更新报告：提交列表 + 变更文件 + 后端移植影响 -->
    <div v-if="reportError" class="error-box report-panel">❌ {{ reportError }}</div>
    <div v-if="report" class="card report-panel">
      <div class="report-heading">
        <strong>更新报告</strong>
        <span class="muted">
          {{ shortSha(report.base_sha) }} → {{ shortSha(report.head_sha) }}
          · 共 {{ report.total_commits }} 个提交 · 生成于 {{ report.generated_at }}
        </span>
      </div>
      <p v-if="report.baseline_note" class="muted">⚠️ {{ report.baseline_note }}</p>

      <template v-if="report.total_commits > 0">
        <div class="report-section-title">提交列表</div>
        <ul class="report-commit-list">
          <li v-for="commit in report.commits" :key="commit.sha">
            <a :href="commit.url" target="_blank" rel="noopener" class="commit-sha">
              {{ shortSha(commit.sha) }}
            </a>
            <span>{{ commit.message }}</span>
            <span class="muted" v-if="commit.author">（{{ commit.author }} · {{ commit.date.slice(0, 10) }}）</span>
          </li>
        </ul>

        <div v-if="report.backend_impacts.length" class="report-section-title">
          对后端移植代码的影响（{{ report.backend_impacts.length }} 个文件）
        </div>
        <ul v-if="report.backend_impacts.length" class="report-impact-list">
          <li v-for="impact in report.backend_impacts" :key="impact.backend_file">
            <code>{{ impact.backend_file }}</code>
            <div class="muted">涉及函数：{{ impact.functions.join('、') }}</div>
          </li>
        </ul>

        <div v-if="report.new_upstream_functions.length" class="report-section-title">
          上游新增/变更、后端尚未接入的函数（{{ report.new_upstream_functions.length }}）
        </div>
        <p v-if="report.new_upstream_functions.length" class="muted report-new-funcs">
          {{ report.new_upstream_functions.join('、') }}
        </p>

        <div class="report-section-title">变更文件</div>
        <details v-for="file in report.files" :key="file.filename" class="report-file">
          <summary>
            <code>{{ file.filename }}</code>
            <span class="muted">
              {{ fileStatusLabel(file.status) }} · +{{ file.additions }} / -{{ file.deletions }}
            </span>
          </summary>
          <pre v-if="file.patch_excerpt">{{ file.patch_excerpt }}</pre>
          <p v-else class="muted">二进制文件或无文本差异</p>
          <p v-if="file.truncated" class="muted">…补丁过长，仅展示前 40 行</p>
        </details>
      </template>
      <p v-else class="muted">已确认版本与上游最新版本一致，没有新的变更。</p>
    </div>
  </div>
</template>

<style scoped>
.datasource-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: #fff7d6;
  border: 1px solid #f0df9a;
  border-radius: 8px;
  font-size: 13px;
  color: #7c5c00;
}
.datasource-banner a {
  color: var(--primary);
  white-space: nowrap;
}
.banner-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.banner-actions .btn {
  font-size: 12px;
  padding: 2px 10px;
}
.report-panel {
  margin-bottom: 12px;
  font-size: 13px;
}
.report-heading {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.report-section-title {
  margin: 12px 0 6px;
  font-weight: 600;
  color: var(--primary);
}
.report-commit-list,
.report-impact-list {
  margin: 0;
  padding-left: 18px;
}
.report-commit-list li {
  margin: 4px 0;
}
.commit-sha {
  font-family: monospace;
  margin-right: 8px;
}
.report-impact-list code {
  font-size: 12px;
}
.report-new-funcs {
  font-family: monospace;
  font-size: 12px;
}
.report-file {
  margin: 6px 0;
}
.report-file summary {
  cursor: pointer;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.report-file pre {
  margin: 6px 0;
  padding: 8px;
  background: #f7f8fa;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 11.5px;
  overflow-x: auto;
  white-space: pre;
}
</style>
