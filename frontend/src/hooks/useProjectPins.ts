import { useCallback, useEffect, useRef, useState } from 'react'
import { listProjectPins, addProjectPin, removeProjectPin } from '../api/projects'
import type { ProjectPin } from '../types/project'

const EMPTY_PINS: ProjectPin[] = []

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
  const [snapshot, setSnapshot] = useState<{ project: string | null; pins: ProjectPin[] }>({ project: null, pins: [] })
  const [loading, setLoading] = useState(false)
  const [failure, setFailure] = useState<{ project: string; message: string } | null>(null)
  const requestVersion = useRef(0)
  const currentProject = useRef(projectUuid)
  currentProject.current = projectUuid
  const pins = snapshot.project === projectUuid ? snapshot.pins : EMPTY_PINS
  const error = failure?.project === projectUuid ? failure.message : null

  const load = useCallback(async () => {
    // A late mutation of an old project must not refresh over the new scope.
    if (currentProject.current !== projectUuid) return
    const version = ++requestVersion.current
    if (!projectUuid) {
      setSnapshot({ project: null, pins: [] })
      setFailure(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setFailure(null)
    try {
      const data = await listProjectPins(projectUuid)
      if (version === requestVersion.current) setSnapshot({ project: projectUuid, pins: data })
    } catch (reason) {
      if (version === requestVersion.current) setFailure({ project: projectUuid, message: reason instanceof Error ? reason.message : 'Could not load project pins.' })
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [projectUuid])

  useEffect(() => { void load(); return () => { requestVersion.current += 1 } }, [load])

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
    await load()
  }, [projectUuid, load])

  const unpin = useCallback(async (pinType: string, targetId: string) => {
    if (!projectUuid) return
    await removeProjectPin(projectUuid, pinType, targetId)
    await load()
  }, [projectUuid, load])

  return { pins, loading: loading || (!!projectUuid && snapshot.project !== projectUuid && !error), error, refresh: load, idsByType, isPinned, pin, unpin }
}
