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

// Upload new version needs edit rights on the existing file; a team member
// without them (a teammate's file in a team folder) can still rename theirs.
const ADVICE = 'To update it, choose Upload new version on the existing file. If you can\u2019t change that file, rename yours and upload it again.'

export function unappliedUploadMessage(
  fileName: string,
  result: DuplicateUploadResult,
  place: 'this folder' | 'your files' = 'this folder',
): string {
  return result.changed
    ? `A different file named \u201c${fileName}\u201d is already in ${place}. It was not replaced, and the file you chose was not uploaded. ${ADVICE}`
    : `A file named \u201c${fileName}\u201d is already in ${place} and was not updated. If yours is a newer version: ${ADVICE.charAt(0).toLowerCase()}${ADVICE.slice(1)}`
}

/** Save a file the app generated (not one the person picked) under a name
 * built from *stem*. When a different file already has that name, the save
 * is repeated with the time added, so newer results are stored rather than
 * silently dropped. `identical`: the same content is already there. */
export async function saveGeneratedFile<R extends DuplicateUploadResult>(
  save: (fileName: string) => Promise<R>,
  stem: string,
  extension: string,
  now: Date = new Date(),
): Promise<{ outcome: 'saved' | 'identical' | 'refused'; fileName: string; result: R }> {
  const settle = (fileName: string, result: R) => ({
    outcome: isUnappliedUpload(result) ? 'refused' as const : result.exists ? 'identical' as const : 'saved' as const,
    fileName, result,
  })
  const first = settle(`${stem}.${extension}`, await save(`${stem}.${extension}`))
  if (first.outcome !== 'refused') return first
  const two = (n: number) => String(n).padStart(2, '0')
  const timed = `${stem}-${two(now.getHours())}${two(now.getMinutes())}${two(now.getSeconds())}.${extension}`
  return settle(timed, await save(timed))
}
