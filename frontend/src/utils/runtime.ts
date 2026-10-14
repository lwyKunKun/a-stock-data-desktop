import type { ReportSource } from '../api/types'

export function getRuntimeSource(): ReportSource {
  return new URLSearchParams(window.location.search).get('client') === 'desktop'
    ? 'desktop'
    : 'web'
}
