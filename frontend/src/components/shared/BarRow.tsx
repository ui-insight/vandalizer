interface BarRowProps {
  label: string
  pct: number
  color: string
  emphasised?: boolean
}

export function BarRow({ label, pct, color, emphasised = false }: BarRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 150, flexShrink: 0, fontSize: 12, lineHeight: 1.3,
        fontWeight: emphasised ? 600 : 400,
        color: emphasised ? 'var(--workspace-text)' : 'var(--workspace-muted)',
      }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 12, backgroundColor: 'var(--workspace-canvas)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', backgroundColor: color }} />
      </div>
      <div style={{
        width: 50, textAlign: 'right',
        fontSize: emphasised ? 16 : 13, fontWeight: emphasised ? 700 : 600,
        color: emphasised ? color : 'var(--workspace-text)',
      }}>
        {pct.toFixed(0)}%
      </div>
    </div>
  )
}
