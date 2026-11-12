import type { CredentialScope } from '../../types/certification'

export function CredentialScopeDescription({ scope }: { scope: CredentialScope }) {
  return <div className="min-w-0 space-y-3 text-sm text-gray-700 [overflow-wrap:anywhere]">
    <p>{scope.promise}</p>
    <p><span className="font-semibold text-gray-900">Agent assistance: </span>{scope.agent_assistance}</p>
    <p className="font-semibold text-gray-900">What this credential does not establish</p>
    <ul className="list-disc space-y-2 pl-5">{scope.exclusions.map(item => <li key={item}>{item}</li>)}</ul>
  </div>
}
