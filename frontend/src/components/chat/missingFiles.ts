/**
 * What chat says when files attached to it can no longer be used (support
 * ticket: a deleted file answered "Document not found: 81C2C3…").
 *
 * Names the files, says why, and says they are off the chat now, so the next
 * send works.
 */
export function missingFilesMessage(names: string[], count: number, reason: 'deleted' | 'unavailable' = 'unavailable'): string {
  const several = count > 1
  const named = names.map(n => `“${n}”`)
  const subject = named.length === 0
    ? (several ? 'Files attached to this chat' : 'A file attached to this chat')
    : named.length === 1 ? named[0]
      : `${named.slice(0, -1).join(', ')} and ${named[named.length - 1]}`
  const why = reason === 'deleted'
    ? `${several ? 'were' : 'was'} deleted`
    : `${several ? 'are' : 'is'} no longer available to you (deleted, or your access changed)`
  return `${subject} ${why}, so ${several ? 'they have' : 'it has'} been removed from this chat. Your message was not sent.`
}
