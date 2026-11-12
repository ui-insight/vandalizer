import { useEffect, useRef } from 'react'

/**
 * Chat's update_workflow replaces a workflow's steps in place. An editor
 * showing that workflow still holds the old steps, so it listens for this
 * signal and reloads.
 */
const EVENT = 'vandalizer:workflow-edited'
// A chat result renders again when its conversation is reopened; announce
// each edit once per page load.
const announced = new Set<string>()

export function announceWorkflowEdited(workflowId: string, key?: string) {
  if (key) {
    if (announced.has(key)) return
    announced.add(key)
  }
  window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: workflowId }))
}

/** Runs *onEdited* when chat edits the workflow *workflowId*. */
export function useOnWorkflowEdited(workflowId: string | null | undefined, onEdited: () => unknown) {
  const latest = useRef(onEdited)
  latest.current = onEdited
  useEffect(() => {
    if (!workflowId) return
    const listener = (event: Event) => {
      if ((event as CustomEvent<string>).detail === workflowId) void latest.current()
    }
    window.addEventListener(EVENT, listener)
    return () => window.removeEventListener(EVENT, listener)
  }, [workflowId])
}
