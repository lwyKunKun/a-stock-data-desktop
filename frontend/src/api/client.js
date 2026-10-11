/** 后端 API 客户端。 */
async function request(path, options = {}) {
  const response = await fetch(path, options)
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `请求失败 (HTTP ${response.status})`)
  }
  return response.json()
}

function get(path, signal) {
  return request(path, { signal })
}

function post(path, body = {}, signal) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

export function fetchQuote(codes) {
  const list = Array.isArray(codes) ? codes.join(',') : codes
  return get(`/api/quote?codes=${encodeURIComponent(list)}`)
}

export function fetchValuation(code) {
  return get(`/api/valuation/${encodeURIComponent(code)}`)
}

export function fetchFundFlow(code) {
  return get(`/api/fundflow/${encodeURIComponent(code)}`)
}

export function fetchConcept(code) {
  return get(`/api/concept/${encodeURIComponent(code)}`)
}

export function fetchSnapshot(code) {
  return get(`/api/snapshot/${encodeURIComponent(code)}`)
}

// ── 全维度纯数据查询（零 token）：采集任务 + 轮询 + 完整数据 ──
export function collectData(code, refresh = false, signal) {
  return post(`/api/data/${encodeURIComponent(code)}/collect`, { refresh }, signal)
}

export function fetchDataStatus(code, signal) {
  return get(`/api/data/${encodeURIComponent(code)}/status`, signal)
}

export function fetchFullData(code, signal) {
  return get(`/api/data/${encodeURIComponent(code)}`, signal)
}

export function fetchAiAnalysis(code, refresh = false) {
  return get(`/api/ai_analysis/${encodeURIComponent(code)}${refresh ? '?refresh=true' : ''}`)
}

export function fetchReportConfig(signal) {
  return get('/api/report/config', signal)
}

export function generateReport(code, refresh = false, signal) {
  return post(`/api/report/${encodeURIComponent(code)}/generate`, { refresh }, signal)
}

export function fetchReportStatus(code, signal) {
  return get(`/api/report/${encodeURIComponent(code)}/status`, signal)
}

export function fetchReport(code, signal) {
  return get(`/api/report/${encodeURIComponent(code)}`, signal)
}

export function retryReportChapter(code, key, signal) {
  return post(
    `/api/report/${encodeURIComponent(code)}/chapter/${encodeURIComponent(key)}/retry`,
    {},
    signal,
  )
}

export function retryReportPublish(code, signal) {
  return post(`/api/report/${encodeURIComponent(code)}/publish/retry`, {}, signal)
}
