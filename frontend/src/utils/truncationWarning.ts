import { useContext } from 'react'
import { AuthContext } from '../contexts/AuthContext'

// Mirrors TRUNCATION_WARNING_PREFIX in backend/app/services/llm_service.py.
// The stored warning names only remedies every user can act on; the admin
// remedy below is appended at render time for admin viewers, because regular
// users cannot open Admin → System Config and a message sending them there
// points at a page that does not exist for them.
export const TRUNCATION_WARNING_PREFIX = 'Output was cut off'

export const TRUNCATION_ADMIN_REMEDY =
  'As an admin, you can also raise “Response reserve (output tokens)” for this model under Admin → System Config → Models.'

export function isTruncationWarning(warning: string | null | undefined): boolean {
  return typeof warning === 'string' && warning.includes(TRUNCATION_WARNING_PREFIX)
}

/** Append the admin-only remedy to a stored step warning when the viewer is an admin. */
export function withAdminRemedy(warning: string, isAdmin: boolean): string {
  if (!isAdmin || !isTruncationWarning(warning)) return warning
  if (warning.includes(TRUNCATION_ADMIN_REMEDY)) return warning
  return `${warning} ${TRUNCATION_ADMIN_REMEDY}`
}

/** Whether the signed-in viewer is a platform admin. Tolerates a missing provider (false). */
export function useIsAdmin(): boolean {
  const ctx = useContext(AuthContext)
  return ctx?.user?.is_admin === true
}
