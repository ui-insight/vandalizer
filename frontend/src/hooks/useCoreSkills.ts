import { useCallback, useEffect, useRef, useState } from 'react'
import { CORE_SKILLS_CHANGED, getCoreSkills, type CoreSkillsPage } from '../api/assistant'
import { useAuth } from './useAuth'

/** Availability depends on the current team, even though the saved list is personal. */
export function useCoreSkills() {
  const { user } = useAuth()
  const signedIn = !!user
  const scope = `${user?.user_id ?? ''}:${user?.current_team ?? ''}`
  const currentScope = useRef(scope)
  currentScope.current = scope
  const sequence = useRef(0)
  const [result, setResult] = useState<{ scope: string; page: CoreSkillsPage | null; error: string; loading: boolean }>({ scope, page: null, error: '', loading: true })

  const replace = useCallback((page: CoreSkillsPage) => {
    if (currentScope.current !== scope) return
    sequence.current++
    setResult({ scope, page, error: '', loading: false })
  }, [scope])

  const refresh = useCallback(async () => {
    const request = ++sequence.current
    setResult(previous => ({ scope, page: previous.scope === scope ? previous.page : null, error: '', loading: true }))
    try {
      const page = await getCoreSkills()
      if (request !== sequence.current || currentScope.current !== scope) return null
      setResult({ scope, page, error: '', loading: false })
      return page
    } catch {
      if (request !== sequence.current || currentScope.current !== scope) return null
      setResult(previous => ({ ...previous, error: 'Could not refresh your core Skills.', loading: false }))
      return null
    }
  }, [scope])

  useEffect(() => {
    if (!signedIn) return
    const refreshVisible = () => { if (document.visibilityState !== 'hidden') void refresh() }
    const storage = (event: StorageEvent) => { if (event.key === CORE_SKILLS_CHANGED) refreshVisible() }
    void refresh()
    const timer = window.setInterval(refreshVisible, 300_000)
    window.addEventListener('focus', refreshVisible)
    window.addEventListener(CORE_SKILLS_CHANGED, refreshVisible)
    window.addEventListener('storage', storage)
    document.addEventListener('visibilitychange', refreshVisible)
    return () => {
      sequence.current++
      clearInterval(timer)
      window.removeEventListener('focus', refreshVisible)
      window.removeEventListener(CORE_SKILLS_CHANGED, refreshVisible)
      window.removeEventListener('storage', storage)
      document.removeEventListener('visibilitychange', refreshVisible)
    }
  }, [scope, refresh, signedIn])

  const visible = result.scope === scope
  return { scope, page: visible ? result.page : null, error: visible ? result.error : '', loading: !visible || result.loading, refresh, replace }
}
