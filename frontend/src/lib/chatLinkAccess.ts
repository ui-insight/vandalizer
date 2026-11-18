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

/** What to say when a link attached some of its items and not others. */
export function describePartialLink(
  { attached, requested, loadFailed }: { attached: number; requested: number; loadFailed: boolean },
): string {
  const missing = requested - attached
  const head = `${attached} of ${requested} items from this link are attached.`
  if (loadFailed) {
    // Some of the missing ones never got an answer, so sharing may not be
    // the reason: don't send the person to ask for access they may have.
    return `${head} The ${missing === 1 ? 'other one' : `other ${missing}`} couldn’t be loaded just now. Check your connection and open the link again.`
  }
  return `${head} ${missing === 1 ? 'The other one isn’t' : `The other ${missing} aren’t`} shared with you. Ask the person who sent it to share ${missing === 1 ? 'it' : 'them'}.`
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
