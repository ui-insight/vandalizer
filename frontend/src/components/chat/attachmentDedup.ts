/**
 * Filename-based dedup for chat file drops.
 *
 * Dropping the same file twice would otherwise upload it twice and create two
 * separate documents (and two OCR jobs). Partition an incoming batch into the
 * files we should upload and the duplicates we should skip, checking both
 * what's already attached and repeats within the same batch.
 */
export function partitionNewFiles(
  fileNames: string[],
  attachedNames: Iterable<string>,
): { toUpload: string[]; dupes: string[] } {
  const attached = new Set(attachedNames)
  const seen = new Set<string>()
  const toUpload: string[] = []
  const dupes: string[] = []
  for (const name of fileNames) {
    if (attached.has(name) || seen.has(name)) {
      dupes.push(name)
    } else {
      seen.add(name)
      toUpload.push(name)
    }
  }
  return { toUpload, dupes }
}
