interface ProgressRowProps {
  label: string
  subtitle: string
  pct: number
  color: string
}

export function ProgressRow({ label, subtitle, pct, color }: ProgressRowProps) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#888', marginBottom: 3 }}>
        <span>{label}</span>
        <span>{subtitle}</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={Math.round(Math.min(100, Math.max(0, pct)))}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ height: 6, backgroundColor: '#2a2a2a', borderRadius: 3, overflow: 'hidden' }}
      >
        <div style={{
          width: `${Math.min(100, Math.max(0, pct))}%`, height: '100%',
          backgroundColor: color, transition: 'width 0.3s',
        }} />
      </div>
    </div>
  )
}
