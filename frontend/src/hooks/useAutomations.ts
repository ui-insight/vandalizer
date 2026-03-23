import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/automations'
import type { Automation } from '../types/automation'

export function useAutomations() {
  const [automations, setAutomations] = useState<Automation[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listAutomations()
      setAutomations(data)
    } catch {
      // errors handled by caller
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const create = async (name: string) => {
    const auto = await api.createAutomation({ name })
    setAutomations(prev => [...prev, auto])
    return auto
  }

  const remove = async (id: string) => {
    await api.deleteAutomation(id)
    setAutomations(prev => prev.filter(a => a.id !== id))
  }

  return { automations, loading, refresh, create, remove }
}
