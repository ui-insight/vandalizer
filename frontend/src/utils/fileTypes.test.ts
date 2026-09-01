import { describe, it, expect } from 'vitest'
import { SUPPORTED_EXTENSIONS, SUPPORTED_ACCEPT_ATTR, isSupportedExtension } from './fileTypes'

/**
 * The upload list and the automation file-type filter drifted apart once
 * already: the filter offered `html` (which no upload can produce, so the
 * automation could never fire) and omitted `md` (which uploads fine).
 *
 * Parity with the server's ALLOWED_EXTS — the only real gate — is asserted
 * from the backend suite (``backend/tests/test_file_type_parity.py``), which
 * can read both files. This side stays free of filesystem access: the frontend
 * has no @types/node, so a node:fs import fails the typecheck and the build.
 */
describe('supported file types', () => {
  it('offers md and does not offer html', () => {
    expect(SUPPORTED_EXTENSIONS).toContain('md')
    expect(SUPPORTED_EXTENSIONS).not.toContain('html')
  })

  it('covers every extension the uploader accepts', () => {
    expect([...SUPPORTED_EXTENSIONS].sort()).toEqual(
      ['csv', 'doc', 'docx', 'md', 'pdf', 'txt', 'xls', 'xlsx'],
    )
  })

  it('builds an accept attribute of dotted extensions', () => {
    expect(SUPPORTED_ACCEPT_ATTR.split(',')).toEqual(
      SUPPORTED_EXTENSIONS.map(e => `.${e}`),
    )
  })

  it('normalizes case and a leading dot', () => {
    expect(isSupportedExtension('.PDF')).toBe(true)
    expect(isSupportedExtension('html')).toBe(false)
  })
})
