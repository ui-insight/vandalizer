/**
 * File-producing workflow steps (Document Renderer, Data Export, Package
 * Builder) return `{type: "file_download", data_b64, filename, file_type}`,
 * and the engine's _format_final_output passes that object through untouched
 * while stringifying everything else. Every place that shows a run's result
 * used to fall back to "pretty-print the object as JSON" for it — a block of
 * internal fields and a wall of base64 shown as the user's deliverable
 * (support ticket). These helpers recognise the payload and describe it as a
 * file: name, type, size, and the decoded text when it is a text file.
 */

export interface FileDownloadPayload {
  type: 'file_download'
  data_b64: string
  filename?: string
  file_type?: string
}

export interface FileOutputSummary {
  filename: string
  /** Lower-case extension-like type: 'docx', 'md', 'csv', … */
  fileType: string
  sizeBytes: number
  /** Decoded UTF-8 content for text-type files, else null (binary: docx/pdf/zip/…). */
  text: string | null
  /** True when `text` was cut at the preview cap. */
  textTruncated: boolean
}

// Types we can show inline. Anything else is a binary the browser can't
// render in a div — the card alone, with the download action, is the result.
const TEXT_TYPES = new Set(['md', 'markdown', 'txt', 'text', 'csv', 'tsv', 'json', 'html', 'htm', 'xml', 'yaml', 'yml'])
const MARKDOWN_TYPES = new Set(['md', 'markdown'])

/** Characters of decoded text kept for the inline preview. */
export const TEXT_PREVIEW_MAX_CHARS = 200_000

export function isFileDownloadPayload(value: unknown): value is FileDownloadPayload {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return v.type === 'file_download' && typeof v.data_b64 === 'string'
}

/** Bytes encoded by a base64 string, without decoding it. */
export function base64ByteLength(b64: string): number {
  const clean = b64.replace(/[\r\n\s]/g, '')
  if (!clean) return 0
  let padding = 0
  if (clean.endsWith('==')) padding = 2
  else if (clean.endsWith('=')) padding = 1
  return Math.max(0, Math.floor((clean.length * 3) / 4) - padding)
}

export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export function isMarkdownType(fileType: string): boolean {
  return MARKDOWN_TYPES.has(fileType.toLowerCase())
}

function decodeBase64Utf8(b64: string): string | null {
  try {
    const binary = atob(b64.replace(/[\r\n\s]/g, ''))
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
  } catch {
    return null
  }
}

function typeFromPayload(p: FileDownloadPayload): string {
  const explicit = (p.file_type || '').trim().toLowerCase().replace(/^\./, '')
  if (explicit) return explicit
  const name = p.filename || ''
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : 'bin'
}

/**
 * Describe a run/step result as a file, or null when it isn't one. Accepts the
 * bare payload or the `{output: payload}` wrapper the status endpoint uses.
 */
export function summarizeFilePayload(value: unknown): FileOutputSummary | null {
  let candidate = value
  if (candidate && typeof candidate === 'object' && !isFileDownloadPayload(candidate)) {
    const inner = (candidate as Record<string, unknown>).output
    if (isFileDownloadPayload(inner)) candidate = inner
  }
  if (!isFileDownloadPayload(candidate)) return null

  const fileType = typeFromPayload(candidate)
  const filename = (candidate.filename || '').trim() || `output.${fileType}`
  const sizeBytes = base64ByteLength(candidate.data_b64)

  let text: string | null = null
  let textTruncated = false
  if (TEXT_TYPES.has(fileType)) {
    const decoded = decodeBase64Utf8(candidate.data_b64)
    if (decoded !== null) {
      textTruncated = decoded.length > TEXT_PREVIEW_MAX_CHARS
      text = textTruncated ? decoded.slice(0, TEXT_PREVIEW_MAX_CHARS) : decoded
    }
  }
  return { filename, fileType, sizeBytes, text, textTruncated }
}

/** One line for places that only have room for text (a save-dialog preview). */
export function describeFileSummary(s: FileOutputSummary): string {
  const size = formatBytes(s.sizeBytes)
  return `${s.filename} (${s.fileType.toUpperCase()}${size ? `, ${size}` : ''})`
}
