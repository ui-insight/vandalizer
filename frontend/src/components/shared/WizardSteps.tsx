interface WizardStepsProps<T extends string> {
  steps: readonly T[]
  current: T
  labels: Record<T, string>
}

export function WizardSteps<T extends string>({ steps, current, labels }: WizardStepsProps<T>) {
  const currentIndex = steps.indexOf(current)
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-4)', marginTop: 'var(--workspace-space-12)' }}>
      {steps.map((s, i) => {
        const active = s === current
        const done = currentIndex > i
        return (
          <div key={s} aria-current={active ? 'step' : undefined} style={{
            flex: '1 1 100px', minWidth: 0, overflowWrap: 'anywhere', padding: "var(--workspace-space-4) var(--workspace-space-6)", textAlign: 'center',
            fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
            color: active ? 'var(--workspace-text)' : done ? 'var(--workspace-accent-ink)' : 'var(--workspace-muted)',
            borderBottom: '2px solid ' + (active ? 'var(--highlight-color, #eab308)' : done ? 'color-mix(in srgb, var(--highlight-color, #eab308) 35%, transparent)' : 'var(--workspace-border)'),
          }}>
            {labels[s]}
          </div>
        )
      })}
    </div>
  )
}
