import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../api/automations'
import type { Automation } from '../types/automation'

export function useAutomations() {
  const [automations, setAutomations] = useState<Automation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestVersion = useRef(0)

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current
    setLoading(true)
    setError(null)
    try {
      const data = await api.listAutomations()
      if (version === requestVersion.current) setAutomations(data)
    } catch (reason) {
      if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : 'Could not load automations.')
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh(); return () => { requestVersion.current += 1 } }, [refresh])

  const create = async (name: string) => {
    const auto = await api.createAutomation({ name })
    setAutomations(prev => [...prev, auto])
    return auto
  }

  const remove = async (id: string) => {
    await api.deleteAutomation(id)
    setAutomations(prev => prev.filter(a => a.id !== id))
  }

  return { automations, loading, error, refresh, create, remove }
}
