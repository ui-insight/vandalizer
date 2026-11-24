import { useCallback, useEffect, useRef, useState } from 'react'
import { getUserConfig, updateUserConfig } from '../api/config'
import type { ModelInfo } from '../types/workflow'

/** Apply a choice to this chat immediately, while serializing default saves. */
export function useChatModelPreference() {
  const [selectedModel, setSelectedModel] = useState('')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<{ kind: 'load' | 'save'; message: string; model?: string } | null>(null)
  const choice = useRef(0)
  const read = useRef(0)
  const mounted = useRef(true)
  const writes = useRef<Promise<unknown>>(Promise.resolve())

  const load = useCallback(async () => {
    const request = ++read.current, version = choice.current
    setError(null)
    try {
      const config = await getUserConfig()
      if (!mounted.current || request !== read.current || version !== choice.current) return
      setModels(config.available_models ?? [])
      setSelectedModel(config.model || config.available_models?.[0]?.tag || '')
    } catch {
      if (mounted.current && request === read.current && version === choice.current) {
        setError({ kind: 'load', message: 'Could not load your saved model. Choose a model for this chat or retry.' })
      }
    }
  }, [])

  const cancelRead = useCallback(() => { mounted.current = false; read.current++ }, [])
  useEffect(() => {
    mounted.current = true
    void load()
    return cancelRead
  }, [load, cancelRead])

  const select = useCallback((model: string, persist = true) => {
    const version = ++choice.current
    setSelectedModel(model)
    setError(null)
    setSaving(persist)
    if (!persist) return
    writes.current = writes.current.catch(() => {}).then(() => mounted.current ? updateUserConfig({ model }) : undefined)
      .then(() => {
        if (mounted.current && version === choice.current) setSaving(false)
      }, () => {
        if (!mounted.current || version !== choice.current) return
        setSaving(false)
        setError({ kind: 'save', model, message: 'Using this model for this chat. Could not save it as your default.' })
      })
  }, [])

  const retry = () => error?.kind === 'save' && error.model ? select(error.model) : void load()
  return { selectedModel, models, setModels, select, saving, error: error?.message ?? null, retry }
}
