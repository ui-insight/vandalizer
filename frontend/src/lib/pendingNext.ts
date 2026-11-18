// Where to go after signing in.
//
// A signed-out visitor who opens a link (say a knowledge base's chat link,
// /?kb=<uuid>) is sent to /landing?next=<link>. Password sign-in stays on that
// page and follows `next`, but university single sign-on leaves the site and
// comes back to "/", so the link was lost and the person landed in a plain
// chat. The sign-in buttons park the link here and the app picks it up on
// return. Session storage keeps it to the tab that asked.

export const PENDING_NEXT_KEY = 'vandalizer:pendingNext'

// Long enough to sign in with a second factor, short enough that an abandoned
// sign-in doesn't redirect a later visit in the same tab.
const MAX_AGE_MS = 10 * 60 * 1000

// Only used to resolve a path; nothing is ever sent to it.
const RESOLVE_BASE = 'https://same-origin.invalid'

function hasControlCharacter(text: string): boolean {
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i)
    if (code <= 0x20 || code === 0x7f) return true
  }
  return false
}

/** A same-origin relative path, or null. Rejects protocol-relative (//host)
 * and absolute URLs so `next` can't be used as an open redirect.
 *
 * A browser drops tabs and newlines when it parses a URL, so "/\t/evil.example"
 * is "//evil.example" by the time it is followed. A path never holds a raw
 * space or control character (they arrive percent-encoded), so one is
 * refused, and the path must still resolve to the origin it was given. */
export function safeNextPath(raw: string | undefined | null): string | null {
  if (!raw) return null
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null
  if (hasControlCharacter(raw)) return null
  try {
    if (new URL(raw, RESOLVE_BASE).origin !== RESOLVE_BASE) return null
  } catch {
    return null
  }
  return raw
}

export function rememberPendingNext(raw: string | undefined | null): void {
  const path = safeNextPath(raw)
  if (!path) return
  try {
    sessionStorage.setItem(PENDING_NEXT_KEY, JSON.stringify({ path, at: Date.now() }))
  } catch {
    // Storage unavailable (private mode, quota): sign-in still works, the
    // link just isn't resumed.
  }
}

/** Forget the parked link. Called when sign-in follows a link directly
 * (password sign-in, or an already signed-in visit): a link parked by an
 * earlier, abandoned single sign-on must not pull the person away from the
 * one they just opened. */
export function clearPendingNext(): void {
  try {
    sessionStorage.removeItem(PENDING_NEXT_KEY)
  } catch {
    // Nothing was parked if storage is unavailable.
  }
}

/** The parked link, removed as it is read. Null when there is none, it has
 * expired, or it isn't a safe path. */
export function consumePendingNext(): string | null {
  let raw: string | null = null
  try {
    raw = sessionStorage.getItem(PENDING_NEXT_KEY)
    if (raw) sessionStorage.removeItem(PENDING_NEXT_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as { path?: unknown; at?: unknown }
    if (typeof parsed.path !== 'string' || typeof parsed.at !== 'number') return null
    if (Date.now() - parsed.at > MAX_AGE_MS) return null
    return safeNextPath(parsed.path)
  } catch {
    return null
  }
}
