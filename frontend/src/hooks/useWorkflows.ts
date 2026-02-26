import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/workflows'
import type { Workflow } from '../types/workflow'

export function useWorkflows(space?: string) {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listWorkflows(space)
      setWorkflows(data)
    } finally {
      setLoading(false)
    }
  }, [space])

  useEffect(() => { refresh() }, [refresh])

  const create = async (name: string, currentSpace?: string) => {
    const wf = await api.createWorkflow({ name, space: currentSpace })
    setWorkflows(prev => [...prev, wf])
    return wf
  }

  const remove = async (id: string) => {
    await api.deleteWorkflow(id)
    setWorkflows(prev => prev.filter(w => w.id !== id))
  }

  const duplicate = async (id: string) => {
    const wf = await api.duplicateWorkflow(id)
    setWorkflows(prev => [...prev, wf])
    return wf
  }

  return { workflows, loading, refresh, create, remove, duplicate }
}
