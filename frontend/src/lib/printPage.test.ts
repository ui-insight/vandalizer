import { afterEach, describe, expect, it, vi } from 'vitest'
import { openPrintPage, withPrintOnLoad } from './printPage'

const PAGE = '<html><head><title>Conversation</title></head><body class="x"><div>hi</div></body></html>'

describe('withPrintOnLoad', () => {
  it('prints on load and says how to print without the script', () => {
    const html = withPrintOnLoad(PAGE)
    expect(html).toMatch(/<body class="x"><p class="print-hint">/)
    expect(html).toMatch(/<script>addEventListener\("load",function\(\)\{print\(\)\}\)<\/script><\/body>/)
    expect(html).toContain('@media print{.print-hint{display:none}}')
  })
})

describe('openPrintPage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('opens the page in its own browsing context, never from the app', () => {
    const open = vi.spyOn(window, 'open')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    URL.createObjectURL = vi.fn(() => 'blob:page')
    URL.revokeObjectURL = vi.fn()

    openPrintPage(PAGE)

    expect(open).not.toHaveBeenCalled()
    expect(click).toHaveBeenCalledOnce()
    const clicked = click.mock.contexts[0] as HTMLAnchorElement
    expect(clicked.href).toBe('blob:page')
    expect(clicked.target).toBe('_blank')
    expect(clicked.rel.split(' ')).toContain('noopener')
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })
})
