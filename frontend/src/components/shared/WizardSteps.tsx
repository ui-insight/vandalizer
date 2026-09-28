interface WizardStepsProps<T extends string> {
  steps: readonly T[]
  current: T
  labels: Record<T, string>
}

export function WizardSteps<T extends string>({ steps, current, labels }: WizardStepsProps<T>) {
  const currentIndex = steps.indexOf(current)
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 12 }}>
      {steps.map((s, i) => {
        const active = s === current
        const done = currentIndex > i
        return (
          <div key={s} aria-current={active ? 'step' : undefined} style={{
            flex: '1 1 100px', minWidth: 0, overflowWrap: 'anywhere', padding: '4px 6px', textAlign: 'center',
            fontSize: 12, fontWeight: 600,
            color: active ? '#fff' : done ? 'var(--highlight-color, #eab308)' : '#b8bec7',
            borderBottom: '2px solid ' + (active ? 'var(--highlight-color, #eab308)' : done ? 'color-mix(in srgb, var(--highlight-color, #eab308) 35%, transparent)' : '#333'),
          }}>
            {labels[s]}
          </div>
        )
      })}
    </div>
  )
}
