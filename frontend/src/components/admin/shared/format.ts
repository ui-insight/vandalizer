export function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return n.toString()
}

export function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms}ms`
  const secs = ms / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  const mins = Math.floor(secs / 60)
  const remainSecs = Math.round(secs % 60)
  return `${mins}m ${remainSecs}s`
}

export function parseUtcDate(d: string): Date {
  // Backend stores UTC but may omit timezone suffix; ensure JS treats it as UTC
  if (!d.endsWith('Z') && !d.includes('+') && !d.includes('-', 10)) return new Date(d + 'Z')
  return new Date(d)
}

export function formatDate(d: string | null): string {
  if (!d) return '—'
  const date = parseUtcDate(d)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatDateTime(d: string | null): string {
  if (!d) return '—'
  const date = parseUtcDate(d)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function downloadCSV(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const escape = (v: string | number | null) => {
    if (v === null || v === undefined) return ''
    let s = String(v)
    // Guard against formula injection: a leading =, +, -, @, tab, or CR can be
    // interpreted as a formula by spreadsheet apps opening the exported CSV.
    if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers.join(','), ...rows.map(r => r.map(escape).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
