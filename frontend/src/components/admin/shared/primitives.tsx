import {
  BarChart3, TrendingUp, TrendingDown, ChevronDown, ChevronUp, ArrowUpDown, Search, Download, RefreshCw,
} from 'lucide-react'

export function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    completed: { bg: '#dcfce7', text: '#166534' },
    failed: { bg: '#fee2e2', text: '#991b1b' },
    error: { bg: '#fee2e2', text: '#991b1b' },
    running: { bg: '#dbeafe', text: '#1e40af' },
    queued: { bg: '#e0e7ff', text: '#3730a3' },
    canceled: { bg: '#fef3c7', text: '#92400e' },
  }
  const c = colors[status] || { bg: '#f3f4f6', text: '#374151' }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
      fontSize: 12, fontWeight: 600, backgroundColor: c.bg, color: c.text,
    }}>
      {status}
    </span>
  )
}

export function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    admin: { bg: '#fef3c7', text: '#92400e' },
    staff: { bg: '#dcfce7', text: '#166534' },
    examiner: { bg: '#dbeafe', text: '#1e40af' },
  }
  const c = colors[role] || { bg: '#f3f4f6', text: '#374151' }
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 9999,
      fontSize: 10, fontWeight: 700, backgroundColor: c.bg, color: c.text,
      textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      {role}
    </span>
  )
}

export function TrendDelta({ current, previous, invert }: { current: number; previous: number; invert?: boolean }) {
  if (previous === 0 && current === 0) return null
  const pct = previous === 0 ? 100 : Math.round(((current - previous) / previous) * 100)
  const isUp = pct > 0
  const isGood = invert ? !isUp : isUp
  if (pct === 0) return <span style={{ fontSize: 11, color: '#9ca3af' }}>0%</span>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 11, fontWeight: 600, color: isGood ? '#16a34a' : '#dc2626' }}>
      {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {isUp ? '+' : ''}{pct}%
    </span>
  )
}

export function KpiCard({ label, value, icon: Icon, color, trend }: {
  label: string; value: string | number; icon: typeof BarChart3; color: string
  trend?: { current: number; previous: number; invert?: boolean }
}) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
      padding: '20px', display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 'var(--ui-radius, 12px)', backgroundColor: color + '18',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={22} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 13, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 500 }}>{label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <div style={{ fontSize: 26, fontWeight: 700, color: '#111827', fontFamily: 'ui-monospace, monospace' }}>{value}</div>
          {trend && <TrendDelta current={trend.current} previous={trend.previous} invert={trend.invert} />}
        </div>
      </div>
    </div>
  )
}

export function UserAvatar({ name }: { name: string | null }) {
  const letter = (name || '?')[0].toUpperCase()
  const hue = (letter.charCodeAt(0) * 37) % 360
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      backgroundColor: `hsl(${hue}, 55%, 88%)`, color: `hsl(${hue}, 55%, 35%)`, fontWeight: 700, fontSize: 14, flexShrink: 0,
    }}>
      {letter}
    </div>
  )
}

export function SortableHeader({ label, sortKey, currentSort, onSort, align = 'left' }: {
  label: string; sortKey: string
  currentSort: { key: string; dir: 'asc' | 'desc' }
  onSort: (key: string) => void
  align?: 'left' | 'right' | 'center'
}) {
  const active = currentSort.key === sortKey
  return (
    <th
      scope="col"
      aria-sort={active ? (currentSort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      style={{
        padding: 0, textAlign: align, whiteSpace: 'nowrap',
      }}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, width: '100%',
          justifyContent: align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start',
          padding: '10px 16px', fontSize: 11, fontWeight: 600, color: '#6b7280',
          textTransform: 'uppercase', cursor: 'pointer', userSelect: 'none',
          background: 'none', border: 'none', fontFamily: 'inherit',
        }}
      >
        {label}
        {active ? (currentSort.dir === 'asc' ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />) : <ArrowUpDown size={10} aria-hidden="true" style={{ opacity: 0.4 }} />}
      </button>
    </th>
  )
}

export function SearchInput({ value, onChange, placeholder, ariaLabel }: { value: string; onChange: (v: string) => void; placeholder: string; ariaLabel?: string }) {
  return (
    <div style={{ position: 'relative', maxWidth: 300 }}>
      <Search size={14} aria-hidden="true" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder ?? 'Search'}
        style={{
          width: '100%', padding: '7px 12px 7px 32px', borderRadius: 'var(--ui-radius, 12px)',
          border: '1px solid #e5e7eb', fontSize: 13, outline: 'none',
        }}
      />
    </div>
  )
}

export function ExportButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px',
        borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
        fontSize: 12, fontWeight: 500, cursor: 'pointer', background: '#fff', color: '#374151',
      }}
    >
      <Download size={13} /> Export CSV
    </button>
  )
}

// Default day options used by every analytics tab. Backend caps at 730d
// (MAX_ANALYTICS_DAYS) so the longest preset stays comfortably below that.
const DAY_OPTIONS = [7, 14, 30, 90, 180, 365] as const
export type DayOption = number | 'all'

export function TimeRangeSelector({
  value,
  onChange,
  options = DAY_OPTIONS as readonly number[],
  includeAll = false,
  onRefresh,
}: {
  value: DayOption
  onChange: (v: DayOption) => void
  options?: readonly number[]
  includeAll?: boolean
  onRefresh?: () => void
}) {
  const opts: DayOption[] = includeAll ? [...options, 'all'] : [...options]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 13, color: '#6b7280', fontWeight: 500 }}>Time Range:</span>
      {opts.map(d => {
        const active = value === d
        const label = d === 'all' ? 'All time' : d >= 365 ? `${Math.round(d / 365)}y` : `${d}d`
        return (
          <button
            key={String(d)}
            onClick={() => onChange(d)}
            style={{
              padding: '5px 14px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
              backgroundColor: active ? 'var(--highlight-color, #eab308)' : '#fff',
              color: active ? 'var(--highlight-text-color, #000)' : '#374151',
            }}
          >
            {label}
          </button>
        )
      })}
      {onRefresh && (
        <button type="button" onClick={onRefresh} aria-label="Refresh" style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}>
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
