import { useCallback, useEffect, useState } from 'react'
import { listProjectPins, addProjectPin, removeProjectPin } from '../api/projects'
import type { ProjectPin } from '../types/project'

/**
 * Loads the pins for a project and exposes helpers for filtering and toggling.
 *
 * Pins are the only thing that ties a workflow/extraction/automation/knowledge
 * base to a project (those entities have no project_uuid of their own), so this
 * hook is what lets the Automations and Knowledge tabs scope themselves to the
 * active project and lets the Explore catalog pin straight into it.
 *
 * Pass `null` (no active project) and it stays inert — empty pins, no fetches.
 */
export function useProjectPins(projectUuid: string | null) {
  const [pins, setPins] = useState<ProjectPin[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    if (!projectUuid) {
      setPins([])
      return
    }
    setLoading(true)
    listProjectPins(projectUuid)
      .then(setPins)
      .catch(() => setPins([]))
      .finally(() => setLoading(false))
  }, [projectUuid])

  useEffect(() => { load() }, [load])

  const idsByType = useCallback(
    (pinType: string) => new Set(pins.filter(p => p.pin_type === pinType).map(p => p.target_id)),
    [pins],
  )

  const isPinned = useCallback(
    (pinType: string, targetId: string) => pins.some(p => p.pin_type === pinType && p.target_id === targetId),
    [pins],
  )

  const pin = useCallback(async (pinType: string, targetId: string) => {
    if (!projectUuid) return
    await addProjectPin(projectUuid, { pin_type: pinType, target_id: targetId })
    load()
  }, [projectUuid, load])

  const unpin = useCallback(async (pinType: string, targetId: string) => {
    if (!projectUuid) return
    await removeProjectPin(projectUuid, pinType, targetId)
    load()
  }, [projectUuid, load])

  return { pins, loading, refresh: load, idsByType, isPinned, pin, unpin }
}
