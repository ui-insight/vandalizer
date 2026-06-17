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
        width: 80, fontSize: 12, fontWeight: emphasised ? 600 : 400,
        color: emphasised ? '#fff' : '#aaa',
      }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 12, backgroundColor: '#1a1a1a', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', backgroundColor: color }} />
      </div>
      <div style={{
        width: 50, textAlign: 'right',
        fontSize: emphasised ? 16 : 13, fontWeight: emphasised ? 700 : 600,
        color: emphasised ? color : '#ddd',
      }}>
        {pct.toFixed(0)}%
      </div>
    </div>
  )
}
