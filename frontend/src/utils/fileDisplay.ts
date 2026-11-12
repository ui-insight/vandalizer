// How a file or folder row describes itself: size, contents, and kind.

const UNITS = ['KB', 'MB', 'GB', 'TB']

/** "812 B", "4.2 MB", "12 MB". Empty string when the size is not known. */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit++
  }
  // Round first: 9.96 must read "10", not "10.0".
  const rounded = Math.round(value * 10) / 10
  return `${rounded >= 10 ? Math.round(value) : rounded} ${UNITS[unit]}`
}

/** "Empty", "1 item", "12 items". Empty string when the count is not known. */
export function formatItemCount(count: number | null | undefined): string {
  if (count == null) return ''
  if (count === 0) return 'Empty'
  return `${count} ${count === 1 ? 'item' : 'items'}`
}

/** "6 folders, 10 files", "1 file", "Empty". */
export function formatContentsSummary(folderCount: number, fileCount: number): string {
  const parts: string[] = []
  if (folderCount > 0) parts.push(`${folderCount} ${folderCount === 1 ? 'folder' : 'folders'}`)
  if (fileCount > 0) parts.push(`${fileCount} ${fileCount === 1 ? 'file' : 'files'}`)
  return parts.length ? parts.join(', ') : 'Empty'
}

export type FileKind = 'pdf' | 'document' | 'spreadsheet' | 'presentation' | 'image' | 'web' | 'other'

const KIND_BY_EXTENSION: Record<string, FileKind> = {
  pdf: 'pdf',
  doc: 'document', docx: 'document', rtf: 'document', odt: 'document', txt: 'document', md: 'document',
  xls: 'spreadsheet', xlsx: 'spreadsheet', xlsm: 'spreadsheet', csv: 'spreadsheet', tsv: 'spreadsheet', ods: 'spreadsheet',
  ppt: 'presentation', pptx: 'presentation',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', tif: 'image', tiff: 'image', bmp: 'image', webp: 'image',
  html: 'web', htm: 'web',
}

export function fileKind(extension: string | null | undefined): FileKind {
  return KIND_BY_EXTENSION[(extension ?? '').replace(/^\./, '').toLowerCase()] ?? 'other'
}
