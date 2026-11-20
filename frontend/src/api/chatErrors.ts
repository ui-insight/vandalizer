/** Files attached to the chat that the server could not find: deleted, or no
 *  longer the caller's to read. Sending the same request again cannot work. */
export class MissingDocumentsError extends Error {
  documentUuids: string[]
  reason: 'deleted' | 'unavailable'

  constructor(message: string, documentUuids: string[], reason: 'deleted' | 'unavailable') {
    super(message)
    this.name = 'MissingDocumentsError'
    this.documentUuids = documentUuids
    this.reason = reason
  }
}
