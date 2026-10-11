// localStorage 持久化封装 —— 上次查询代码 + 查询历史记录
// 历史记录上限 20 条，按查询时间倒序（最新在前），同一代码去重

export interface HistoryItem {
  code: string
  name: string
  time: string // ISO 时间串
}

const LAST_QUERY_KEY = 'last_query_code'
const HISTORY_KEY = 'search_history'
const HISTORY_LIMIT = 20

function readHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is HistoryItem =>
        typeof item === 'object'
        && item !== null
        && typeof (item as HistoryItem).code === 'string',
    )
  } catch {
    return []
  }
}

function writeHistory(items: HistoryItem[]): void {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items))
}

export function loadLastQuery(): string {
  return localStorage.getItem(LAST_QUERY_KEY) ?? ''
}

export function saveLastQuery(code: string): void {
  localStorage.setItem(LAST_QUERY_KEY, code)
}

export function loadHistory(): HistoryItem[] {
  return readHistory()
}

export function addHistory(code: string, name = ''): HistoryItem[] {
  const rest = readHistory().filter((item) => item.code !== code)
  const items = [{ code, name, time: new Date().toISOString() }, ...rest]
  writeHistory(items.slice(0, HISTORY_LIMIT))
  return items
}

export function removeHistory(code: string): HistoryItem[] {
  const items = readHistory().filter((item) => item.code !== code)
  writeHistory(items)
  return items
}

export function clearHistory(): void {
  localStorage.removeItem(HISTORY_KEY)
}
