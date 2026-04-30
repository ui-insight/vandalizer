export const PENDING_INVITE_TOKEN_KEY = 'vandalizer:pendingInviteToken'

export function consumePendingInviteToken(): string | null {
  const token = sessionStorage.getItem(PENDING_INVITE_TOKEN_KEY)
  if (token) sessionStorage.removeItem(PENDING_INVITE_TOKEN_KEY)
  return token
}
