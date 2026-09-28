import type { KBOptimizationRun, OptimizationTrial } from '../../api/knowledge'
import { OptimizationProgressCard } from '../shared/OptimizationProgressCard'
import { summariseConfigVerbose } from './OptimizationResults'

interface Props {
  run: KBOptimizationRun
  onCancel: () => void
  cancelling: boolean
}

export function OptimizationProgress({ run, onCancel, cancelling }: Props) {
  return (
    <OptimizationProgressCard<OptimizationTrial['config']>
      run={run}
      scoreFloor={run.baseline_default_score}
      summariseConfig={summariseConfigVerbose}
      onCancel={onCancel}
      cancelling={cancelling}
      scoreFloorLabel="Default settings: composite quality"
      scoreFloorDescription="Retrieval and answer quality on the same test questions used for the trials."
      liftLabel="vs default settings"
    />
  )
}
