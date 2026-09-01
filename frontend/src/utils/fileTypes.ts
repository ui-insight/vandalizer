/**
 * The file types this deployment accepts, in one place.
 *
 * Mirrors ``ALLOWED_EXTS`` in ``backend/app/utils/file_validation.py`` — the
 * server rejects anything else, so every surface that offers a file type
 * (upload inputs, pickers, the folder-watch automation filter) must offer
 * exactly this set. They used to keep private copies, and drifted: the
 * automation filter offered `html`, which no upload can produce, while `md`
 * uploaded fine but couldn't be filtered on.
 */
export const SUPPORTED_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'md']

/** Value for a file input's `accept` attribute (".pdf,.doc,…"). */
export const SUPPORTED_ACCEPT_ATTR = SUPPORTED_EXTENSIONS.map(e => `.${e}`).join(',')

export function isSupportedExtension(ext: string): boolean {
  return SUPPORTED_EXTENSIONS.includes(ext.toLowerCase().replace(/^\./, ''))
}
