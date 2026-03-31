import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from './useAuth'
import {
  getPendingPrompt,
  showPrompt as apiShowPrompt,
  dismissPrompt as apiDismissPrompt,
  type PendingPrompt,
  type ShowPromptResult,
} from '../api/feedbackPrompt'

const POLL_INTERVAL = 60_000 // 60 seconds
const INITIAL_DELAY = 5_000 // 5 seconds after mount

export interface FeedbackPromptResult {
  pendingPrompt: PendingPrompt | null
  loading: boolean
  /** Create the support ticket and return its uuid. */
  showPrompt: () => Promise<ShowPromptResult | null>
  /** Dismiss the prompt so it won't appear again. */
  dismissPrompt: () => Promise<void>
  /** Clear the pending prompt from local state (e.g. after navigating to the ticket). */
  clearPending: () => void
}

export function useFeedbackPrompt(): FeedbackPromptResult {
  const { user } = useAuth()
  const [pendingPrompt, setPendingPrompt] = useState<PendingPrompt | null>(null)
  const [loading, setLoading] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined)
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const isDemoUser = user?.is_demo_user ?? false

  const fetchPending = useCallback(async () => {
    if (!isDemoUser) return
    try {
      const res = await getPendingPrompt()
      setPendingPrompt(res.prompt)
    } catch {
      // Silent — don't disrupt the user
    }
  }, [isDemoUser])

  useEffect(() => {
    if (!isDemoUser) {
      setPendingPrompt(null)
      return
    }

    // Initial delay before first check
    timeoutRef.current = setTimeout(() => {
      fetchPending()
      intervalRef.current = setInterval(fetchPending, POLL_INTERVAL)
    }, INITIAL_DELAY)

    return () => {
      clearTimeout(timeoutRef.current)
      clearInterval(intervalRef.current)
    }
  }, [isDemoUser, fetchPending])

  const showPrompt = useCallback(async (): Promise<ShowPromptResult | null> => {
    if (!pendingPrompt) return null
    setLoading(true)
    try {
      const result = await apiShowPrompt(pendingPrompt.slug)
      setPendingPrompt(null)
      return result
    } catch {
      return null
    } finally {
      setLoading(false)
    }
  }, [pendingPrompt])

  const dismissPrompt = useCallback(async () => {
    if (!pendingPrompt) return
    try {
      await apiDismissPrompt(pendingPrompt.slug)
    } catch {
      // Silent
    }
    setPendingPrompt(null)
  }, [pendingPrompt])

  const clearPending = useCallback(() => {
    setPendingPrompt(null)
  }, [])

  return { pendingPrompt, loading, showPrompt, dismissPrompt, clearPending }
}
