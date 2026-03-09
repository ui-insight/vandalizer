import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/knowledge'
import type { KnowledgeBase } from '../types/knowledge'

export function useKnowledgeBases() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listKnowledgeBases()
      setKnowledgeBases(data)
    } catch {
      // errors handled by caller
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const create = async (title: string, description?: string) => {
    const kb = await api.createKnowledgeBase(title, description)
    setKnowledgeBases(prev => [kb, ...prev])
    return kb
  }

  const remove = async (uuid: string) => {
    await api.deleteKnowledgeBase(uuid)
    setKnowledgeBases(prev => prev.filter(k => k.uuid !== uuid))
  }

  return { knowledgeBases, loading, refresh, create, remove }
}
