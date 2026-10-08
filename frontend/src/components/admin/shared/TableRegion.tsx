import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

/** Wide records retain usable columns and expose both mouse and keyboard scrolling. */
export function TableRegion({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const hintId = useId()
  const [overflow, setOverflow] = useState(false)
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
    {overflow && <p id={hintId} className="admin-scroll-hint">More columns to the right. Scroll horizontally, or focus the table and use the arrow keys.</p>}
    <div ref={ref} className="admin-table-region" role="region" aria-label={label} aria-describedby={overflow ? hintId : undefined} tabIndex={0}>{children}</div>
  </>
}
