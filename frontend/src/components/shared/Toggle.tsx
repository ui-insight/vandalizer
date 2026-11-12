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
        display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-12)',
        padding: "var(--workspace-space-8) var(--workspace-space-12)", width: '100%', textAlign: 'left',
        backgroundColor: checked && !disabled ? 'var(--workspace-selected)' : 'transparent',
        border: '1px solid ' + (checked && !disabled ? 'var(--workspace-accent-ink)' : 'var(--workspace-border)'),
        borderRadius: 'var(--workspace-radius-small)', cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1, marginBottom: 'var(--workspace-space-6)', fontFamily: 'inherit', color: 'var(--workspace-text)',
      }}
    >
      <span style={{
        width: 16, height: 16, borderRadius: 'var(--workspace-radius-small)', marginTop: 'var(--workspace-space-2)',
        background: checked ? 'var(--highlight-color, #eab308)' : 'transparent',
        border: '1.5px solid ' + (checked ? 'var(--workspace-accent-ink)' : 'var(--workspace-border)'),
        flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {checked && <span style={{ color: 'var(--highlight-text-color, #000)', fontSize: 'var(--workspace-font-meta)' }}>✓</span>}
      </span>
      <div>
        <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 500 }}>{label}</div>
        {description && <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', marginTop: 'var(--workspace-space-2)' }}>{description}</div>}
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
      border: '2px solid ' + (active ? 'var(--workspace-accent-ink)' : 'var(--workspace-border)'),
      backgroundColor: active ? 'var(--highlight-color, #eab308)' : 'transparent',
      flexShrink: 0,
    }} />
  )
}
