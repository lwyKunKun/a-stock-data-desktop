<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { searchUsStocks } from '../api/client'
import type { UsSearchItem } from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

const US_SYMBOL_RE = /^[A-Z][A-Z0-9]{0,13}(?:[.-][A-Z0-9]{1,4})?$/
type SearchMode = 'suggest' | 'submit'
const emit = defineEmits<{ select: [item: UsSearchItem] }>()
const query = ref('')
const items = ref<UsSearchItem[]>([])
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null
let requestId = 0
let submittingQuery: string | null = null

function cancelSearch(): void {
  if (timer) clearTimeout(timer)
  timer = null
  requestId += 1
  controller?.abort()
  controller = null
  submittingQuery = null
  loading.value = false
}

function choose(item: UsSearchItem): void {
  cancelSearch()
  query.value = item.symbol
  items.value = []
  error.value = ''
  emit('select', item)
}

function submit(): void {
  const term = query.value.trim()
  if (!term) {
    cancelSearch()
    items.value = []
    error.value = '请输入美股代码或公司名。'
    return
  }

  const symbol = term.toUpperCase()
  if (US_SYMBOL_RE.test(symbol)) {
    choose({ market: 'US', symbol, name: symbol, asset_type: 'stock' })
    return
  }

  if (submittingQuery === term) return
  cancelSearch()
  void search(term, 'submit')
}

function schedule(): void {
  cancelSearch()
  items.value = []
  error.value = ''
  const term = query.value.trim()
  if (!term) return
  timer = setTimeout(() => {
    timer = null
    void search(term, 'suggest')
  }, 300)
}

async function search(term: string, mode: SearchMode): Promise<void> {
  const isSubmit = mode === 'submit'
  const currentId = ++requestId
  controller?.abort()
  const currentController = new AbortController()
  controller = currentController
  submittingQuery = isSubmit ? term : null
  loading.value = true
  error.value = ''
  items.value = []

  try {
    const results = (await searchUsStocks(term, currentController.signal)).items
    if (currentId !== requestId) return
    if (isSubmit) {
      if (!results.length) {
        error.value = `未找到与“${term}”匹配的美股，请尝试输入股票代码或更完整的公司名。`
        return
      }
      choose(results[0])
      return
    }
    items.value = results
  } catch (caught: unknown) {
    if (currentId !== requestId || isAbortError(caught)) return
    error.value = isSubmit ? '美股搜索失败，请稍后重试。' : errorMessage(caught)
  } finally {
    if (currentId === requestId) {
      controller = null
      submittingQuery = null
      loading.value = false
    }
  }
}

onBeforeUnmount(cancelSearch)
</script>

<template>
  <div class="us-stock-search">
    <div class="us-search-row">
      <input v-model="query" class="input" placeholder="输入美股代码或公司名，如 AAPL / 英伟达" @input="schedule" @keyup.enter="submit" />
      <button class="btn btn-primary" :disabled="loading" @click="submit">{{ loading ? '搜索中…' : '查询' }}</button>
    </div>
    <div v-if="items.length" class="us-search-results">
      <button v-for="item in items" :key="`${item.exchange}-${item.symbol}`" type="button" @click="choose(item)">
        <strong>{{ item.symbol }}</strong><span>{{ item.name }}</span><small>{{ item.exchange }}</small>
      </button>
    </div>
    <p v-if="error" class="error-box">{{ error }}</p>
  </div>
</template>
