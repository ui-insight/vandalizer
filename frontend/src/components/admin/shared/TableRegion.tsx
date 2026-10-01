import type { ReactNode } from 'react'

/** Keep wide administrative data in a named, keyboard-scrollable region. */
export function TableRegion({ label, children }: { label: string; children: ReactNode }) {
  return <div className="admin-table-region" role="region" aria-label={label} tabIndex={0}>{children}</div>
}
