// Client-side image downscaling for branding uploads (logo / icon / mascot).
//
// Branding images are stored as base64 data URLs directly on the SystemConfig
// document and re-fetched on every page load, so they are capped at a small
// encoded size (see MAX_LOGO_BYTES in Admin.tsx and config.py). Rather than
// rejecting oversized uploads, we transparently shrink them on a canvas until
// they fit, so a user can drop in a 1–2 MB export and have it "just work".

export interface ConstrainOptions {
  /** Hard ceiling on the resulting data URL's length, in bytes. */
  maxBytes: number
  /** Longest side (px) for the first downscale attempt. */
  maxDimension: number
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(reader.error || new Error('Failed to read file'))
    reader.readAsDataURL(file)
  })
}

function loadImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Failed to decode image'))
    img.src = dataUrl
  })
}

function drawToDataUrl(
  img: HTMLImageElement,
  maxDimension: number,
  mime: string,
  quality: number,
): string {
  const longest = Math.max(img.width, img.height) || 1
  const scale = Math.min(1, maxDimension / longest)
  const width = Math.max(1, Math.round(img.width * scale))
  const height = Math.max(1, Math.round(img.height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas not supported')

  // JPEG has no alpha channel; flatten onto white so transparent regions
  // don't render black. PNG/WebP preserve transparency, so leave them be.
  if (mime === 'image/jpeg') {
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, width, height)
  }
  ctx.drawImage(img, 0, 0, width, height)
  return canvas.toDataURL(mime, quality)
}

/**
 * Read an image File and return a data URL that fits under `maxBytes`.
 *
 * - Files already under the cap are returned untouched (no quality loss).
 * - SVGs are returned as-is — they are vector and usually tiny; rasterizing
 *   them on a canvas would defeat the point. The caller should keep its own
 *   size check as a safety net for the rare oversized SVG.
 * - Raster images are downscaled and re-encoded, stepping dimension and
 *   quality down until they fit. Transparency is preserved (WebP) for sources
 *   that may have an alpha channel; opaque sources re-encode as JPEG.
 *
 * Throws if the image cannot be brought under the cap.
 */
export async function fileToConstrainedDataUrl(
  file: File,
  { maxBytes, maxDimension }: ConstrainOptions,
): Promise<string> {
  const original = await readFileAsDataUrl(file)

  if (file.type === 'image/svg+xml') return original
  if (original.length <= maxBytes) return original

  const img = await loadImage(original)

  // PNG/WebP may carry transparency that icons and mascots rely on, so keep an
  // alpha-capable format (WebP compresses far better than PNG at parity).
  const mayHaveAlpha = file.type === 'image/png' || file.type === 'image/webp'
  const mime = mayHaveAlpha ? 'image/webp' : 'image/jpeg'

  let dimension = Math.min(maxDimension, Math.max(img.width, img.height))
  for (let step = 0; step < 8 && dimension >= 64; step++) {
    for (const quality of [0.9, 0.8, 0.7, 0.6]) {
      const candidate = drawToDataUrl(img, dimension, mime, quality)
      if (candidate.length <= maxBytes) return candidate
    }
    dimension = Math.round(dimension * 0.8)
  }

  throw new Error('Could not compress image under the size limit. Try a smaller image.')
}
