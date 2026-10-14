import type {
  DataTaskStatus,
  DatasourceReport,
  DatasourceStatus,
  FullDataResponse,
  FullReport,
  JsonObject,
  PortingApplyResult,
  PortingSuggestion,
  ReportListResponse,
  ReportSource,
  ReportTaskStatus,
  SettingsStatus,
  SettingsUpdate,
  SnapshotResponse,
} from './types'

interface ApiErrorBody {
  detail: string
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === 'object'
    && value !== null
    && 'detail' in value
    && typeof value.detail === 'string'
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    throw new Error(isApiErrorBody(payload) ? payload.detail : `请求失败 (HTTP ${response.status})`)
  }
  return response.json() as Promise<T>
}

function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal })
}

function post<T>(path: string, body: JsonObject = {}, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

function put<T>(path: string, body: JsonObject = {}, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

export function fetchQuote(codes: string | string[]): Promise<Record<string, JsonObject>> {
  const list = Array.isArray(codes) ? codes.join(',') : codes
  return get(`/api/quote?codes=${encodeURIComponent(list)}`)
}

export function fetchValuation(code: string): Promise<JsonObject> {
  return get(`/api/valuation/${encodeURIComponent(code)}`)
}

export function fetchFundFlow(code: string): Promise<JsonObject> {
  return get(`/api/fundflow/${encodeURIComponent(code)}`)
}

export function fetchConcept(code: string): Promise<JsonObject> {
  return get(`/api/concept/${encodeURIComponent(code)}`)
}

export function fetchSnapshot(code: string): Promise<SnapshotResponse> {
  return get(`/api/snapshot/${encodeURIComponent(code)}`)
}

export function collectData(
  code: string,
  refresh = false,
  signal?: AbortSignal,
): Promise<DataTaskStatus> {
  return post(`/api/data/${encodeURIComponent(code)}/collect`, { refresh }, signal)
}

export function fetchDataStatus(code: string, signal?: AbortSignal): Promise<DataTaskStatus> {
  return get(`/api/data/${encodeURIComponent(code)}/status`, signal)
}

export function fetchFullData(code: string, signal?: AbortSignal): Promise<FullDataResponse> {
  return get(`/api/data/${encodeURIComponent(code)}`, signal)
}

export function fetchAiAnalysis(code: string, refresh = false): Promise<JsonObject> {
  return get(`/api/ai_analysis/${encodeURIComponent(code)}${refresh ? '?refresh=true' : ''}`)
}

export function generateReport(
  code: string,
  refresh: boolean,
  source: ReportSource,
  signal?: AbortSignal,
): Promise<ReportTaskStatus> {
  return post(`/api/report/${encodeURIComponent(code)}/generate`, { refresh, source }, signal)
}

export function fetchReportStatus(code: string, signal?: AbortSignal): Promise<ReportTaskStatus> {
  return get(`/api/report/${encodeURIComponent(code)}/status`, signal)
}

export function fetchReport(
  code: string,
  date?: string,
  signal?: AbortSignal,
): Promise<FullReport | null> {
  const params = new URLSearchParams()
  if (date) params.set('date', date)
  const query = params.size ? `?${params.toString()}` : ''
  return get(`/api/report/${encodeURIComponent(code)}${query}`, signal)
}

export function retryReportChapter(
  code: string,
  key: string,
  signal?: AbortSignal,
): Promise<ReportTaskStatus> {
  return post(
    `/api/report/${encodeURIComponent(code)}/chapter/${encodeURIComponent(key)}/retry`,
    {},
    signal,
  )
}

interface ReportListQuery {
  date?: string
  industry?: string
  page?: number
  pageSize?: number
}

export function fetchReportList(
  query: ReportListQuery = {},
  signal?: AbortSignal,
): Promise<ReportListResponse> {
  const params = new URLSearchParams()
  if (query.date) params.set('date', query.date)
  if (query.industry) params.set('industry', query.industry)
  params.set('page', String(query.page ?? 1))
  params.set('page_size', String(query.pageSize ?? 10))
  return get(`/api/report/list?${params.toString()}`, signal)
}

export function fetchDatasourceStatus(signal?: AbortSignal): Promise<DatasourceStatus> {
  return get('/api/datasource/status', signal)
}

export function ackDatasourceUpdate(signal?: AbortSignal): Promise<DatasourceStatus> {
  return post('/api/datasource/ack', {}, signal)
}

export function fetchDatasourceReport(signal?: AbortSignal): Promise<DatasourceReport> {
  return post('/api/datasource/report', {}, signal)
}

export function generatePortingSuggestion(
  cacheKey: string,
  refresh = false,
  signal?: AbortSignal,
): Promise<PortingSuggestion> {
  return post('/api/datasource/porting/generate', { cache_key: cacheKey, refresh }, signal)
}

export function applyPortingSuggestion(
  cacheKey: string,
  files: string[],
  signal?: AbortSignal,
): Promise<PortingApplyResult> {
  return post('/api/datasource/porting/apply', { cache_key: cacheKey, files }, signal)
}

export function fetchSettings(signal?: AbortSignal): Promise<SettingsStatus> {
  return get('/api/settings', signal)
}

export function saveSettings(
  update: SettingsUpdate,
  signal?: AbortSignal,
): Promise<SettingsStatus> {
  return put('/api/settings', update as JsonObject, signal)
}
