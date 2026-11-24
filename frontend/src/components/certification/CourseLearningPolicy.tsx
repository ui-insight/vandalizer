import type { CourseDefinition } from '../../types/certification'
import { CredentialScopeDescription } from './CredentialScopeDescription'

export function CourseLearningPolicy({ course }: { course: Pick<CourseDefinition, 'progression_policy' | 'credential_scope'> }) {
  const policy = course.progression_policy
  const scope = course.credential_scope
  if (!policy && !scope) return null
  return <>{scope && <details className="my-4 min-w-0 rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-700 [overflow-wrap:anywhere]">
    <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">Course goal and certificate scope</summary>
    {scope.state === 'design_draft' && <p className="my-3 font-medium text-gray-900">Unpublished course goal. This preview cannot award a credential.</p>}
    <CredentialScopeDescription scope={scope} />
  </details>}{policy && <details className="my-4 min-w-0 rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-700 [overflow-wrap:anywhere]">
    <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">How learning and credit work</summary>
    {policy.state === 'design_draft' && <p className="mt-2 font-medium text-gray-900">Unpublished draft policy. This preview cannot award course credit.</p>}
    <p className="mt-3">{policy.required_modules} required modules · {policy.required_outcomes} required outcomes · {policy.base_xp_total} total base XP</p>
    <ul className="mt-3 list-disc space-y-3 pl-5">{policy.rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
  </details>}</>
}
