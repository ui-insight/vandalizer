import type { ConnectedRequest } from '../../types/connectedWorkflow'
import type { BudgetRequest } from '../../types/budgetWorkflow'
import type { OutputRequest } from '../../types/outputWorkflow'
import type { ValidationRequest } from '../../types/validationSuite'
import type { BatchRequest } from '../../types/batchAssessment'
import type { GovernanceRequest } from '../../types/governanceAssessment'

type Action = 'design' | 'approval' | (ConnectedRequest | BudgetRequest | OutputRequest | ValidationRequest | BatchRequest | GovernanceRequest)['action']
export type CourseRequestPhase = 'checking' | 'sending' | null
const descriptions: Record<Action, string> = {
  design: 'process design', approval: 'workflow approval', capture: 'input capture', prepare: 'run preparation', scope: 'scope decision',
  execute: 'execution', finalize: 'saved-result finalization', review: 'review decision',
  recovery: 'recovery decision', calculation: 'calculation', inspection: 'file inspection',
  handoff: 'private handoff', suite: 'validation expectations', correction: 'scope correction',
  finding: 'source finding', memo: 'memo preparation', release: 'release decision',
}

export function CourseRequestStatus({ phase, action }: { phase: CourseRequestPhase; action?: Action }) {
  if (!phase) return null
  return <div className="min-w-0 space-y-2 text-sm text-gray-700">
    <p role="status">{phase === 'checking' ? 'Checking the saved state…' : `Sending the ${action ? descriptions[action] : 'original'} request and waiting for its saved result…`}</p>
    <p>{phase === 'checking'
      ? 'This check does not start, repeat or grade work.'
      : 'Closing this panel does not confirm whether the request finished or stopped. Reopen the same work and check the pending request before retrying. Saved results remain available.'}</p>
  </div>
}
