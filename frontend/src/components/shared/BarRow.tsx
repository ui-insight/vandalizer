interface BarRowProps {
  label: string
  pct: number
  color: string
  emphasised?: boolean
}

export function BarRow({ label, pct, color, emphasised = false }: BarRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)' }}>
      <div style={{
        width: 150, flexShrink: 0, fontSize: 'var(--workspace-font-meta)', lineHeight: 1.3,
        fontWeight: emphasised ? 600 : 400,
        color: emphasised ? 'var(--workspace-text)' : 'var(--workspace-muted)',
      }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 12, backgroundColor: 'var(--workspace-canvas)', borderRadius: 'var(--workspace-radius-small)', overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', backgroundColor: color }} />
      </div>
      <div style={{
        width: 50, textAlign: 'right',
        fontSize: emphasised ? 'var(--workspace-font-card-title)' : 'var(--workspace-font-control)', fontWeight: emphasised ? 700 : 600,
        color: emphasised ? color : 'var(--workspace-text)',
      }}>
        {pct.toFixed(0)}%
      </div>
    </div>
  )
}
