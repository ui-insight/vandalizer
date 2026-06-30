interface ToggleProps {
  label: string
  description?: string
  checked: boolean
  onChange?: (b: boolean) => void
  disabled?: boolean
}

export function Toggle({ label, description, checked, onChange, disabled = false }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange?.(!checked)}
      disabled={disabled}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '8px 10px', width: '100%', textAlign: 'left',
        backgroundColor: checked && !disabled ? 'rgba(124, 58, 237, 0.08)' : 'transparent',
        border: '1px solid ' + (checked && !disabled ? 'rgba(124, 58, 237, 0.3)' : '#2a2a2a'),
        borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1, marginBottom: 6, fontFamily: 'inherit', color: '#e5e5e5',
      }}
    >
      <span style={{
        width: 16, height: 16, borderRadius: 4, marginTop: 2,
        background: checked ? '#7c3aed' : 'transparent',
        border: '1.5px solid ' + (checked ? '#7c3aed' : '#555'),
        flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {checked && <span style={{ color: '#fff', fontSize: 11 }}>✓</span>}
      </span>
      <div>
        <div style={{ fontSize: 12, fontWeight: 500 }}>{label}</div>
        {description && <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>{description}</div>}
      </div>
    </button>
  )
}

interface RadioProps {
  active: boolean
}

export function Radio({ active }: RadioProps) {
  return (
    <span style={{
      width: 14, height: 14, borderRadius: '50%',
      border: '2px solid ' + (active ? '#7c3aed' : '#555'),
      backgroundColor: active ? '#7c3aed' : 'transparent',
      flexShrink: 0,
    }} />
  )
}
