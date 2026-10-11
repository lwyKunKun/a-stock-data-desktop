export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export interface JsonObject {
  [key: string]: JsonValue
}

export interface Progress {
  done: number
  total: number
}

export interface SnapshotResponse {
  code: string
  [key: string]: unknown
}

export interface DataChapter {
  key: string
  title: string
  data_md: string
}

export type DataTaskState = 'pending' | 'aggregating' | 'done' | 'failed'

export interface DataTaskStatus {
  task_id?: string
  code: string
  status: DataTaskState
  cached?: boolean
  already_running?: boolean
  reused_report?: boolean
  current_chapter?: string | null
  progress?: Progress
  error?: string | null
  fetched_at?: string
  created_at?: string
  updated_at?: string
  pid?: number
}

export interface FullDataResponse {
  code: string
  name: string
  fetched_at: string
  cached: boolean
  chapters: DataChapter[]
  errors: Record<string, string[]>
  source_errors: Record<string, string>
  snapshot: JsonObject
}

export type ChapterState =
  | 'pending'
  | 'fetching'
  | 'data_ok'
  | 'data_failed'
  | 'generating'
  | 'ok'
  | 'comment_failed'

export interface ReportChapter {
  key: string
  title: string
  state: ChapterState
  data_md?: string
  comment_md?: string
  error?: string
  usage?: Record<string, number>
}

export type ReportTaskState =
  | 'pending'
  | 'aggregating'
  | 'generating'
  | 'assembling'
  | 'retrying'
  | 'done'
  | 'done_with_warnings'
  | 'failed'

export interface ReportTaskStatus {
  task_id?: string
  code?: string
  operation?: string
  status: ReportTaskState
  cached?: boolean
  already_running?: boolean
  current_chapter?: string | null
  chapters?: ReportChapter[]
  progress?: Progress
  error?: string | null
  created_at?: string
  updated_at?: string
  pid?: number
}

export interface ReportMeta {
  code?: string
  name?: string
  generated_at?: string
  model?: string
  duration_s?: number
  usage?: Record<string, number>
  [key: string]: unknown
}

export interface FullReport {
  code: string
  name: string
  meta: ReportMeta
  chapters: ReportChapter[]
  snapshot: JsonObject
  full_markdown: string
}

export interface ReportListItem {
  code: string
  name: string
  date: string
  industry: string
  generated_at: string
  model: string
  total_tokens: number
  duration_s: number
  price: number | null
  change_pct: number | null
  pe_ttm: number | null
}

export interface ReportListResponse {
  items: ReportListItem[]
  dates: string[]
  industries: string[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface DatasourceCommit {
  sha: string
  message: string | null
  date: string | null
  author: string | null
  url: string
}

export interface DatasourceStatus {
  repo: string
  commits_url: string
  latest: DatasourceCommit | null
  acknowledged_sha: string | null
  update_available: boolean
  checked_at: string
  check_ok: boolean
  error: string | null
}

export interface DatasourceReportCommit {
  sha: string
  message: string
  date: string
  author: string
  url: string
}

export interface DatasourceReportFile {
  filename: string
  status: string
  additions: number
  deletions: number
  patch_excerpt: string
  truncated: boolean
}

export interface DatasourceBackendImpact {
  backend_file: string
  functions: string[]
}

export interface DatasourceReport {
  base_sha: string
  head_sha: string
  baseline_note: string | null
  total_commits: number
  commits: DatasourceReportCommit[]
  files: DatasourceReportFile[]
  backend_impacts: DatasourceBackendImpact[]
  new_upstream_functions: string[]
  generated_at: string
}
