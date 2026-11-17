// The extension's page tools (chrome-extension/background/page-tools.js),
// run under jsdom: what browser_click refuses, and where numbers are found.
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { clickRef, readPage } from '../../../chrome-extension/background/page-tools.js'

beforeAll(() => {
  // jsdom lays nothing out; treat every element as drawn except
  // display:contents wrappers, which really have no boxes.
  vi.spyOn(Element.prototype, 'getClientRects').mockImplementation(function (this: Element) {
    const rects = (this as HTMLElement).style?.display === 'contents' ? [] : [{}]
    return rects as unknown as DOMRectList
  })
  Element.prototype.scrollIntoView = vi.fn()
  if (!globalThis.CSS?.escape) vi.stubGlobal('CSS', { escape: (s: string) => s.replace(/["\\]/g, '\\$&') })
})

afterEach(() => { document.body.innerHTML = '' })

/** Put html on the page, number it as one read would, click its first control. */
function click(html: string): Record<string, unknown> {
  document.body.innerHTML = html
  const target = document.querySelector('[data-test]') ?? document.querySelector('a, button, input, [role]')!
  target.setAttribute('data-vz-ref', '1')
  const clicked = vi.fn()
  target.addEventListener('click', (event) => { event.preventDefault(); clicked() })
  const outcome = clickRef(1)
  expect(Boolean(outcome.ok)).toBe(clicked.mock.calls.length === 1)
  return outcome
}

describe('browser_click refuses controls that could write', () => {
  it.each([
    ['an icon button whose aria-label says Approve', '<button aria-label="Approve">✓</button>'],
    ['a button with no readable label', '<button>✓</button>'],
    ['a checkbox outside any filter', '<label><input type="checkbox"> I certify this report</label>'],
    ['a notifications switch', '<div role="switch" aria-checked="false">Email me</div>'],
    ['a toggle button', '<button aria-pressed="false">Notifications</button>'],
    ['"Go" on a form that posts', '<form method="post" action="/change"><input type="submit" value="Go"></form>'],
    ['a plain submit on a posting form', '<form method="post"><button>Continue</button></form>'],
    ['a link to a delete address', '<a href="/items/5/delete">X</a>'],
    ['a sign-out link', '<a href="/logout">Exit</a>'],
    ['a link labelled Approve', '<a href="/awards/5">Approve</a>'],
    ['Save with "Change" in its name', '<button>Save changes</button>'],
    ['Apply outside a filter', '<div><button>Apply</button></div>'],
  ])('%s', (_name, html) => {
    expect(click(html).error).toMatch(/blocked_write_action|unlabeled_control/)
  })
})

describe('browser_click allows ordinary navigation and filters', () => {
  it.each([
    ['a "Purchase Orders" link', '<a href="/finance/po">Purchase Orders</a>'],
    ['a "Change Requests" tab', '<div role="tab">Change Requests</div>'],
    ['a "Purchase Orders" button', '<button type="button">Purchase Orders</button>'],
    ['"Submit" on a search form that sends GET', '<form action="/search"><input name="q"><input data-test type="submit" value="Submit"></form>'],
    ['"Search" on a form that posts', '<form method="post"><button>Search</button></form>'],
    ['"Next" paging on a form that posts', '<form method="post"><input type="submit" value="Next"></form>'],
    ['"Apply" in a filter panel', '<div class="date-filter"><button type="button">Apply</button></div>'],
    ['"Add filter"', '<button type="button">Add filter</button>'],
    ['a checkbox in a search form', '<form action="/search"><label><input type="checkbox"> Active only</label></form>'],
  ])('%s', (_name, html) => {
    expect(click(html).ok).toBe(true)
  })
})

describe('reading and finding numbered controls', () => {
  it('reads what sits inside display:contents wrappers', () => {
    document.body.innerHTML = '<div style="display:contents"><p>Remaining balance 15,000.00</p><a href="/award/1">Award 1</a></div>'
    const page = readPage('', 20000)
    expect(page.text).toContain('Remaining balance 15,000.00')
    expect(page.text).toMatch(/\[1\] link/)
  })

  it('clears numbers left in nested frames, so an old number is never clicked', () => {
    document.body.innerHTML = '<iframe></iframe>'
    const outer = (document.querySelector('iframe') as HTMLIFrameElement).contentDocument!
    outer.body.innerHTML = '<iframe></iframe>'
    const inner = (outer.querySelector('iframe') as HTMLIFrameElement).contentDocument!
    inner.body.innerHTML = '<a href="/old" data-vz-ref="1">Old link</a>'
    readPage('', 20000)
    expect(inner.querySelector('[data-vz-ref]')).toBeNull()
  })

  it('finds a numbered control inside a shadow root', () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const button = document.createElement('button')
    button.textContent = 'Show details'
    button.setAttribute('data-vz-ref', '4')
    host.attachShadow({ mode: 'open' }).appendChild(button)
    expect(clickRef(4)).toMatchObject({ ok: true })
  })
})
