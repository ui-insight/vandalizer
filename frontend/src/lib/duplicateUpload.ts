// What to say when an upload matches the name of a file already in the same
// place. The server keeps the existing file and stores nothing; it reports
// whether the bytes differ. Treating that as a successful upload opened (or
// attached) the old content with no word that the new file was ignored.

export interface DuplicateUploadResult {
  exists?: boolean
  /** true: different content. false: identical. null/absent: not known. */
  changed?: boolean | null
}

/** True when the upload was a same-name file that is not known to be
 * identical — the case that must not pass as a successful upload. */
export function isUnappliedUpload(result: DuplicateUploadResult): boolean {
  return !!result.exists && result.changed !== false
}

export const IDENTICAL_UPLOAD_NOTE = 'Already here with the same content. Nothing was changed.'

const ADVICE = 'To use the new one, rename it or delete the existing file first, then upload again.'

export function unappliedUploadMessage(
  fileName: string,
  result: DuplicateUploadResult,
  place: 'this folder' | 'your files' = 'this folder',
): string {
  return result.changed
    ? `A different file named \u201c${fileName}\u201d is already in ${place}. It was not replaced, and the file you chose was not uploaded. ${ADVICE}`
    : `A file named \u201c${fileName}\u201d is already in ${place} and was not updated. If yours is a newer version: ${ADVICE.charAt(0).toLowerCase()}${ADVICE.slice(1)}`
}
