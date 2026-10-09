import { useEffect, useRef, useState } from 'react'
import { downloadCSV } from './format'

type Page<T> = { items: T[]; total: number }
type Props<T> = {
  scope: string
  filename: string
  headers: string[]
  fetchPage: (offset: number) => Promise<Page<T>>
  getKey: (item: T) => string
  select?: (items: T[]) => T[]
  row: (item: T, index: number) => (string | number | null)[]
  metadata: Record<string, string>
  disabled?: boolean
}

/** Download only after every page succeeds. Changing scope cancels the old job. */
export function FullExportButton<T>(props: Props<T>) {
  return <ExportJob key={props.scope} {...props} />
}

function ExportJob<T>({ filename, headers, fetchPage, getKey, select, row, metadata, disabled }: Props<T>) {
  const active = useRef<{ cancelled: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => () => { if (active.current) active.current.cancelled = true }, [])
  const cancel = () => {
    if (active.current) active.current.cancelled = true
    active.current = null
    setBusy(false)
    setMessage('Export cancelled. No file was downloaded.')
  }
  const start = async () => {
    if (active.current) return
    const run = { cancelled: false }
    active.current = run
    setBusy(true)
    setError('')
    setMessage('Preparing all matching records…')
    try {
      const items: T[] = []
      const keys = new Set<string>()
      let total: number | undefined
      do {
        const page = await fetchPage(items.length)
        if (run.cancelled) return
        if (!Number.isSafeInteger(page.total) || page.total < 0 || (total !== undefined && total !== page.total)) throw new Error('The inventory changed during export. Retry to get a complete file.')
        total = page.total
        for (const item of page.items) {
          const key = getKey(item)
          if (keys.has(key)) throw new Error('The inventory changed during export. Retry to get a complete file.')
          keys.add(key)
          items.push(item)
        }
        if (items.length > total || (!page.items.length && items.length < total)) throw new Error('The export returned an incomplete page. Retry to get a complete file.')
        setMessage(`Preparing export: ${items.length} of ${total} records read.`)
      } while (items.length < total)
      const selected = select ? select(items) : items
      if (run.cancelled) return
      downloadCSV(filename, [...headers, ...Object.keys(metadata)], selected.map((item, index) => [...row(item, index), ...Object.values(metadata)]))
      setMessage(`Downloaded ${selected.length} matching records. Export reflects the records read during this request.`)
    } catch (reason) {
      if (!run.cancelled) { setError(reason instanceof Error ? reason.message : 'Export failed. Retry to get a complete file.'); setMessage('No file was downloaded.') }
    } finally {
      if (active.current === run) { active.current = null; setBusy(false) }
    }
  }
  return <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, maxWidth: '100%' }}>
    <button type="button" className="admin-open-record" disabled={disabled || busy} onClick={() => void start()}>Export all matching records</button>
    {busy && <button type="button" className="admin-open-record" onClick={cancel}>Cancel export</button>}
    {message && <span role="status" style={{ fontSize: 12 }}>{message}</span>}
    {error && <span role="alert" style={{ fontSize: 12, color: '#991b1b' }}>{error}</span>}
  </div>
}
