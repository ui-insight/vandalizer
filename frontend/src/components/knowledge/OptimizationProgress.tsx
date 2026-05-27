import type { KBOptimizationRun, OptimizationTrial } from '../../api/knowledge'
import { OptimizationProgressCard } from '../shared/OptimizationProgressCard'
import { DOMAIN_LABELS } from '../shared/labels'
import { summariseConfigVerbose } from './OptimizationResults'

interface Props {
  run: KBOptimizationRun
  onCancel: () => void
  cancelling: boolean
}

export function OptimizationProgress({ run, onCancel, cancelling }: Props) {
  const labels = DOMAIN_LABELS.kb
  return (
    <OptimizationProgressCard<OptimizationTrial['config']>
      run={run}
      scoreFloor={run.baseline_no_kb_score}
      summariseConfig={summariseConfigVerbose}
      onCancel={onCancel}
      cancelling={cancelling}
      scoreFloorLabel={labels.scoreFloorLabel}
      scoreFloorDescription={labels.scoreFloorDescription}
      liftLabel={labels.liftLabel}
    />
  )
}
