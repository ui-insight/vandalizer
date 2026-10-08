import { createContext, useContext, useEffect, useState } from 'react'

export const ConfigDraftContext = createContext<{
  names: string[]
  report: (name: string, dirty: boolean) => void
} | null>(null)

/** Drafts stay in component memory; credentials are never put in browser storage.
 * markSaved captures the submitted render, so edits made during a request stay dirty.
 */
export function useConfigDraft(name: string, value: unknown, ready = true) {
  const snapshot = JSON.stringify(value)
  const [baseline, setBaseline] = useState<string | null>(ready ? snapshot : null)
  const report = useContext(ConfigDraftContext)?.report
  useEffect(() => {
    if (!ready) setBaseline(null)
    else if (baseline === null) setBaseline(snapshot)
  }, [ready, baseline, snapshot])
  const dirty = ready && baseline !== null && snapshot !== baseline
  useEffect(() => { report?.(name, dirty) }, [report, name, dirty])
  useEffect(() => () => report?.(name, false), [report, name])
  return { dirty, markSaved: () => setBaseline(snapshot) }
}
