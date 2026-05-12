export const PENDING_INVITE_TOKEN_KEY = 'vandalizer:pendingInviteToken'
export const PENDING_JOIN_LINK_TOKEN_KEY = 'vandalizer:pendingJoinLinkToken'

export function consumePendingInviteToken(): string | null {
  const token = sessionStorage.getItem(PENDING_INVITE_TOKEN_KEY)
  if (token) sessionStorage.removeItem(PENDING_INVITE_TOKEN_KEY)
  return token
}

export function consumePendingJoinLinkToken(): string | null {
  const token = sessionStorage.getItem(PENDING_JOIN_LINK_TOKEN_KEY)
  if (token) sessionStorage.removeItem(PENDING_JOIN_LINK_TOKEN_KEY)
  return token
}
