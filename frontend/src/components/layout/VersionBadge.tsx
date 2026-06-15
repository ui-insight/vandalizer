import { useEffect, useState } from 'react'
import { getVersionInfo, type VersionInfo } from '../../api/config'

// A dot color cue so the running environment is recognizable at a glance —
// the whole point of the badge is telling deployments apart.
function envDotColor(environment: string): string {
  if (environment === 'production') return 'bg-green-500'
  if (environment === 'staging') return 'bg-amber-500'
  return 'bg-gray-400'
}

// Compact deployment/version indicator shown in the global Header (the chrome
// shared by every authenticated page via PageLayout / WorkspaceLayout), so users
// can tell which environment + build they're on across deployments.
export function VersionBadge() {
  const [info, setInfo] = useState<VersionInfo | null>(null)

  useEffect(() => {
    let active = true
    // Must .catch(): an uncaught rejection here surfaces as a Sentry
    // "Request failed" on every page load if the endpoint hiccups.
    getVersionInfo()
      .then((v) => { if (active) setInfo(v) })
      .catch(() => { /* non-critical chrome; stay hidden on error */ })
    return () => { active = false }
  }, [])

  if (!info) return null

  return (
    <div
      className="hidden items-center gap-1.5 text-xs text-gray-400 sm:flex"
      title={`Environment: ${info.environment} · Build: ${info.version}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${envDotColor(info.environment)}`} aria-hidden />
      <span className="font-medium text-gray-500">{info.deployment_label}</span>
      <span className="text-gray-300">·</span>
      <span className="font-mono">{info.version}</span>
    </div>
  )
}
