interface WizardStepsProps<T extends string> {
  steps: readonly T[]
  current: T
  labels: Record<T, string>
}

export function WizardSteps<T extends string>({ steps, current, labels }: WizardStepsProps<T>) {
  const currentIndex = steps.indexOf(current)
  return (
    <div style={{ display: 'flex', gap: 4, marginTop: 12 }}>
      {steps.map((s, i) => {
        const active = s === current
        const done = currentIndex > i
        return (
          <div key={s} style={{
            flex: 1, padding: '4px 6px', textAlign: 'center',
            fontSize: 10, fontWeight: 600,
            color: active ? '#fff' : done ? '#a78bfa' : '#666',
            borderBottom: '2px solid ' + (active ? '#a78bfa' : done ? '#7c3aed55' : '#333'),
          }}>
            {labels[s]}
          </div>
        )
      })}
    </div>
  )
}
