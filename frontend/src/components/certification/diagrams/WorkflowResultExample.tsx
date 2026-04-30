const STAGES = [
  {
    label: 'Step 1: Extract',
    color: 'bg-blue-50 border-blue-200',
    labelColor: 'text-blue-700',
    output: '{ "pi_name": "Dr. Chen", "budget": "$485,000", "sections": ["aims", "budget", "biosketch"] }',
  },
  {
    label: 'Step 2: Analyze',
    color: 'bg-purple-50 border-purple-200',
    labelColor: 'text-purple-700',
    output: 'Budget within NSF limits. All required sections present. No compliance gaps found.',
  },
  {
    label: 'Step 3: Report',
    color: 'bg-green-50 border-green-200',
    labelColor: 'text-green-700',
    output: 'Compliance checklist generated. Ready for download.',
  },
]

export function WorkflowResultExample() {
  return (
    <div className="space-y-1 text-xs mt-2">
      {STAGES.map((stage, i) => (
        <div key={i}>
          <div className={`p-2.5 rounded-lg border ${stage.color}`}>
            <div className={`text-[10px] font-bold uppercase tracking-wider mb-1 ${stage.labelColor}`}>
              {stage.label}
            </div>
            <p className="text-gray-700 font-mono text-[10px] leading-relaxed">{stage.output}</p>
          </div>
          {i < STAGES.length - 1 && (
            <div className="flex justify-center my-0.5 text-gray-400 text-sm select-none">↓</div>
          )}
        </div>
      ))}
    </div>
  )
}
