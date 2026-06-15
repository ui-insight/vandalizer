import { useEffect, useState } from 'react'
import { getVersionInfo, type VersionInfo } from '../../api/config'

// A dot color cue so the running environment is recognizable at a glance —
// the whole point of the footer is telling deployments apart.
function envDotColor(environment: string): string {
  if (environment === 'production') return 'bg-green-500'
  if (environment === 'staging') return 'bg-amber-500'
  return 'bg-gray-400'
}

export function VersionFooter() {
  const [info, setInfo] = useState<VersionInfo | null>(null)

  useEffect(() => {
    let active = true
    // Must .catch(): an uncaught rejection here surfaces as a Sentry
    // "Request failed" on every page load if the endpoint hiccups.
    getVersionInfo()
      .then((v) => { if (active) setInfo(v) })
      .catch(() => { /* version footer is non-critical; stay hidden on error */ })
    return () => { active = false }
  }, [])

  if (!info) return null

  return (
    <div
      className="border-t border-gray-200 px-4 py-2.5 text-xs text-gray-400"
      title={`Environment: ${info.environment}`}
    >
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${envDotColor(info.environment)}`} aria-hidden />
        <span className="truncate font-medium text-gray-500">{info.deployment_label}</span>
      </div>
      <div className="mt-0.5 font-mono text-gray-400">{info.version}</div>
    </div>
  )
}
