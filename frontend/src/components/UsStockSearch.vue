<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { searchUsStocks } from '../api/client'
import type { UsSearchItem } from '../api/types'
import { errorMessage, isAbortError } from '../utils/errors'

const emit = defineEmits<{ select: [item: UsSearchItem] }>()
const query = ref('')
const items = ref<UsSearchItem[]>([])
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let controller: AbortController | null = null

function submit(): void {
  const symbol = query.value.trim().toUpperCase()
  if (!symbol) return
  emit('select', { market: 'US', symbol, name: symbol, asset_type: 'stock' })
  items.value = []
}

function schedule(): void {
  if (timer) clearTimeout(timer)
  if (!query.value.trim()) { items.value = []; return }
  timer = setTimeout(() => void search(), 300)
}

async function search(): Promise<void> {
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try { items.value = (await searchUsStocks(query.value.trim(), controller.signal)).items }
  catch (caught: unknown) { if (!isAbortError(caught)) error.value = errorMessage(caught) }
  finally { loading.value = false }
}

function choose(item: UsSearchItem): void {
  query.value = item.symbol; items.value = []; emit('select', item)
}

onBeforeUnmount(() => { if (timer) clearTimeout(timer); controller?.abort() })
</script>

<template>
  <div class="us-stock-search">
    <div class="us-search-row">
      <input v-model="query" class="input" placeholder="输入美股代码或公司名，如 AAPL / Apple" @input="schedule" @keyup.enter="submit" />
      <button class="btn btn-primary" :disabled="loading" @click="submit">查询</button>
    </div>
    <div v-if="items.length" class="us-search-results">
      <button v-for="item in items" :key="`${item.exchange}-${item.symbol}`" type="button" @click="choose(item)">
        <strong>{{ item.symbol }}</strong><span>{{ item.name }}</span><small>{{ item.exchange }}</small>
      </button>
    </div>
    <p v-if="error" class="error-box">{{ error }}</p>
  </div>
</template>
