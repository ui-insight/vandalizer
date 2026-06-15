import { useEffect, useState } from 'react'
import { getVersionInfo, type VersionInfo } from '../../api/config'

// A dot color cue so the running environment is recognizable at a glance.
function envDotColor(environment: string): string {
  if (environment === 'production') return 'bg-green-500'
  if (environment === 'staging') return 'bg-amber-500'
  return 'bg-gray-400'
}

// Non-interactive footer rendered at the bottom of the account dropdown so users
// can confirm which environment + build they're on, without putting it in the
// always-visible header chrome. Renders its own divider; nothing when not loaded.
export function VersionMenuFooter() {
  const [info, setInfo] = useState<VersionInfo | null>(null)

  useEffect(() => {
    let active = true
    // Must .catch(): an uncaught rejection here surfaces as a Sentry
    // "Request failed" if the endpoint hiccups.
    getVersionInfo()
      .then((v) => { if (active) setInfo(v) })
      .catch(() => { /* non-critical; just omit the footer */ })
    return () => { active = false }
  }, [])

  if (!info) return null

  return (
    <>
      <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />
      <div className="px-3.5 py-1.5 text-xs text-gray-400" title={`Environment: ${info.environment}`}>
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${envDotColor(info.environment)}`} aria-hidden />
          <span className="font-medium text-gray-500">{info.deployment_label}</span>
        </div>
        <div className="mt-0.5 font-mono">{info.version}</div>
      </div>
    </>
  )
}
