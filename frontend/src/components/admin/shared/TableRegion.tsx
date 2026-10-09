import { useLayoutEffect, useEffect, useId, useRef, useState, type ReactNode } from 'react'

/** Wide records retain usable columns and expose both mouse and keyboard scrolling. */
export function TableRegion({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const hintId = useId()
  const [overflow, setOverflow] = useState(false)
  const [summary, setSummary] = useState(true)
  useLayoutEffect(() => {
    const table = ref.current?.querySelector('table')
    if (!table) return
    table.setAttribute('role', 'table')
    table.querySelectorAll('thead, tbody').forEach(group => group.setAttribute('role', 'rowgroup'))
    table.querySelectorAll('tr').forEach(row => row.setAttribute('role', 'row'))
    const headers = [...table.querySelectorAll('thead th')].map(header => {
      header.setAttribute('role', 'columnheader')
      return header.textContent?.trim() || 'Details'
    })
    table.querySelectorAll('tbody tr').forEach(row => {
      let column = 0
      row.querySelectorAll(':scope > td').forEach(cell => {
        cell.setAttribute('role', 'cell')
        const span = Number(cell.getAttribute('colspan') || 1)
        cell.setAttribute('data-column-label', span === 1 ? headers[column] || 'Details' : '')
        column += span
      })
    })
  }, [children])
  useEffect(() => {
    const region = ref.current
    if (!region) return
    const measure = () => setOverflow(region.scrollWidth > region.clientWidth + 1)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(region)
    if (region.firstElementChild) observer.observe(region.firstElementChild)
    return () => observer.disconnect()
  }, [children])
  return <>
    <div className="admin-table-view-toggle"><span>Record layout</span><button type="button" aria-pressed={summary} onClick={() => setSummary(true)}>Summary view</button><button type="button" aria-pressed={!summary} onClick={() => setSummary(false)}>Table view</button></div>
    {overflow && <p className={summary ? 'admin-scroll-hint admin-table-hint--summary' : 'admin-scroll-hint'} id={hintId}>More columns to the right. Scroll horizontally, or focus the table and use the arrow keys.</p>}
    <div ref={ref} className={`admin-table-region${summary ? ' admin-table-summary' : ''}`} role="region" aria-label={label} aria-describedby={overflow ? hintId : undefined} tabIndex={0}>{children}</div>
  </>
}
