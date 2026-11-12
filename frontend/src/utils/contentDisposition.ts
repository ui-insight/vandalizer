/**
 * The filename a download response names, read the way a browser reads it:
 * the UTF-8 `filename*` first, then the plain `filename`. The server sends
 * both, and the plain one is an ASCII stand-in, so reading only that turned
 * "Year-by-Year Budget — …" into "Year-by-Year Budget …".
 */
export function filenameFromDisposition(header: string | null | undefined, fallback: string): string {
  const value = header ?? ''
  const encoded = value.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)
  if (encoded) {
    try {
      const name = decodeURIComponent(encoded[1].trim())
      if (name) return name
    } catch { /* malformed escape: use the plain name */ }
  }
  const plain = value.match(/filename\s*=\s*"([^"]*)"/i) ?? value.match(/filename\s*=\s*([^;]+)/i)
  return plain?.[1].trim() || fallback
}
