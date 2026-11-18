// What to tell someone when a chat link (/?kb=…&docs=…&folders=…) attaches
// nothing. The link grants no access, so an item the opener can't see is
// refused by the server; the chat must say so rather than open as an ordinary
// chat that looks like it worked.

import { ApiError } from '../api/client'

/** True when the server answered "you can't see this" (or it no longer
 * exists), as opposed to the request failing to get an answer. */
export function isAccessRefusal(reason: unknown): boolean {
  return reason instanceof ApiError && (reason.status === 403 || reason.status === 404)
}

export function describeLinkFailure(
  { kbs, docs, folders, loadFailed }: { kbs: number; docs: number; folders: number; loadFailed: boolean },
): string {
  if (loadFailed) {
    return 'This link couldn’t be opened just now, so nothing from it is attached to this chat. Check your connection and open the link again.'
  }
  if (kbs + docs + folders > 1) {
    return 'None of the items in this chat link are shared with you. Ask the person who sent it to share them.'
  }
  const item = kbs ? 'knowledge base' : docs ? 'document' : 'folder'
  return `The ${item} in this link isn’t shared with you, so this chat won’t use it. Ask the person who sent the link to share it with you.`
}
