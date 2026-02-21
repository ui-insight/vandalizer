import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/automations'
import type { Automation } from '../types/automation'

export function useAutomations(space?: string) {
  const [automations, setAutomations] = useState<Automation[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listAutomations(space)
      setAutomations(data)
    } catch (err) {
      console.error('Failed to fetch automations:', err)
    } finally {
      setLoading(false)
    }
  }, [space])

  useEffect(() => { refresh() }, [refresh])

  const create = async (name: string, currentSpace?: string) => {
    const auto = await api.createAutomation({ name, space: currentSpace })
    setAutomations(prev => [...prev, auto])
    return auto
  }

  const remove = async (id: string) => {
    await api.deleteAutomation(id)
    setAutomations(prev => prev.filter(a => a.id !== id))
  }

  return { automations, loading, refresh, create, remove }
}
