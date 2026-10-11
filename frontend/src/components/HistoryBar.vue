<!--
  HistoryBar.vue —— 查询历史记录
  展示最近查询过的股票（localStorage 持久化，最多 20 条），
  点击标签重新查询，支持单条删除和清空全部。
-->
<script setup lang="ts">
import { ref } from 'vue'
import { clearHistory, loadHistory, removeHistory } from '../utils/storage'
import type { HistoryItem } from '../utils/storage'

const emit = defineEmits<{ select: [code: string] }>()

const items = ref<HistoryItem[]>(loadHistory())

function refresh(): void {
  items.value = loadHistory()
}

function select(code: string): void {
  emit('select', code)
}

function remove(code: string): void {
  items.value = removeHistory(code)
}

function clearAll(): void {
  clearHistory()
  items.value = []
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${mm}`
}

defineExpose({ refresh })
</script>

<template>
  <div v-if="items.length" class="card history-bar">
    <div class="history-header">
      <span class="muted">查询历史（{{ items.length }}）</span>
      <button class="btn btn-ghost" @click="clearAll">清空</button>
    </div>
    <div class="tags">
      <span
        v-for="item in items"
        :key="item.code"
        class="tag history-tag"
        :title="`查询于 ${formatTime(item.time)}`"
        @click="select(item.code)"
      >
        {{ item.name ? `${item.name} ${item.code}` : item.code }}
        <span
          class="history-remove"
          title="删除这条记录"
          @click.stop="remove(item.code)"
        >×</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.history-bar {
  padding: 10px 14px;
}
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}
.history-header .btn {
  font-size: 12px;
  padding: 2px 8px;
}
.history-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.history-remove {
  color: var(--text-light);
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}
.history-remove:hover {
  color: var(--up);
}
</style>
