// The extension's page tools (chrome-extension/background/page-tools.js),
// run under jsdom: what browser_click refuses, and where numbers are found.
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
// Loaded as text and evaluated, like the other extension tests. A typed
// import of a file outside frontend/ fails `tsc -b` in the Docker build,
// whose context is frontend/ alone, so the image could not be built.
import toolsScript from '../../../chrome-extension/background/page-tools.js?raw'

type Outcome = Record<string, unknown>
const { clickRef, readPage, selectRef, typeRef } = new Function(
  `${toolsScript.replaceAll('export function', 'function')}\nreturn { clickRef, readPage, selectRef, typeRef };`,
)() as {
  clickRef: (ref: number) => Outcome
  typeRef: (ref: number, text: string) => Outcome
  selectRef: (ref: number, option: string) => Outcome
  readPage: (query: string, maxChars: number) => { text: string } & Outcome
}

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
  it('routes new-window links through the working tab and still checks the action first', () => {
    expect(click('<a target="_blank" href="https://example.edu/search">Directory</a>')).toMatchObject({ open_url: 'https://example.edu/search' })
    expect(click('<a target="_blank" href="https://example.edu/delete">Delete</a>')).toMatchObject({ error: 'blocked_write_action' })
  })

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

// Independent review of the first version: each of these was clicked, typed
// or chosen, while the permission window promised "Read-only".
describe('browser_click refuses what the first word list missed', () => {
  it.each([
    ['Mark as complete', '<button type="button">Mark as complete</button>'],
    ['Publish', '<button type="button">Publish</button>'],
    ['Yes', '<button type="button">Yes</button>'],
    ['OK', '<button type="button">OK</button>'],
    ['Continue', '<button type="button">Continue</button>'],
    ['Buy now', '<button type="button">Buy now</button>'],
    ['Unsubscribe', '<button type="button">Unsubscribe</button>'],
    ['Revoke access', '<button type="button">Revoke access</button>'],
    ['Disable account', '<button type="button">Disable account</button>'],
    ['Reset password', '<button type="button">Reset password</button>'],
    ['Share', '<button type="button">Share</button>'],
    ['Enroll', '<button type="button">Enroll</button>'],
    ['a role=button "Terminate award"', '<div role="button">Terminate award</div>'],
    ['a link to an archive address', '<a href="/awards/12/archive">Old awards</a>'],
    ['a link to a disable address', '<a href="/users/5/disable">User 5</a>'],
    ['a link with action=mark_paid', '<a href="/invoices/7?action=mark_paid">Invoice 7</a>'],
    ['"View and finish" in a posting form', '<form method="post"><button>View and finish</button></form>'],
    ['a named button inside a dialog', '<div role="dialog"><button type="button">Transactions</button></div>'],
    ['a named button inside a posting form', '<form method="post"><button type="button">Transactions</button></form>'],
  ])('%s', (_name, html) => {
    expect(click(html).error).toBe('blocked_write_action')
  })

  it.each([
    ['a menu button', '<button type="button" aria-haspopup="menu">Account</button>'],
    ['an expander', '<button type="button" aria-expanded="false">Budget lines</button>'],
    ['"Close" on a dialog', '<div role="dialog"><button type="button">Close</button></div>'],
    ['"View details" in a dialog', '<div role="dialog"><button type="button">View details</button></div>'],
    ['a named view button', '<button type="button">Transactions</button>'],
  ])('still clicks %s', (_name, html) => {
    expect(click(html).ok).toBe(true)
  })
})

/** Put html on the page and number its [data-test] control (or first field) as 1. */
function field(html: string): HTMLElement {
  document.body.innerHTML = html
  const target = (document.querySelector('[data-test]') ?? document.querySelector('input, textarea, select')) as HTMLElement
  target.setAttribute('data-vz-ref', '1')
  return target
}

describe('browser_type and browser_select only work in search and filter fields', () => {
  it.each([
    ['a comment box', '<form method="post"><textarea name="comment"></textarea><button>Save</button></form>'],
    ['a text field in a form that saves', '<form method="post"><input name="title"><button>Update</button></form>'],
    ['a field outside any form or filter', '<input name="amount">'],
  ])('does not type in %s', (_name, html) => {
    const el = field(html) as HTMLInputElement
    const changed = vi.fn()
    el.addEventListener('change', changed)
    expect(typeRef(1, 'x')).toMatchObject({ error: 'blocked_write_action' })
    expect(el.value).toBe('')
    expect(changed).not.toHaveBeenCalled()
  })

  it.each([
    ['a search box', '<input type="search" name="q">'],
    ['a field in a GET form', '<form action="/search"><input name="term"></form>'],
    ['a field named for a filter', '<input name="awardFilter">'],
    ['a field in a filter panel', '<div class="search-criteria"><input name="fund"></div>'],
    ['a field in a posting form that only searches', '<form method="post"><input name="fund"><input type="submit" value="Search"></form>'],
  ])('types in %s', (_name, html) => {
    const el = field(html) as HTMLInputElement
    expect(typeRef(1, '123456')).toMatchObject({ ok: true })
    expect(el.value).toBe('123456')
  })

  it.each([
    ['a status drop-down in a form that saves', '<form method="post"><label>Status <select name="status"><option>Open</option><option>Closed</option></select></label><button>Save</button></form>'],
    ['a status drop-down that saves on change', '<label>Status <select name="status"><option>Open</option><option>Closed</option></select></label>'],
  ])('does not choose in %s', (_name, html) => {
    const el = field(html) as HTMLSelectElement
    const changed = vi.fn()
    el.addEventListener('change', changed)
    expect(selectRef(1, 'Closed')).toMatchObject({ error: 'blocked_write_action' })
    expect(el.value).toBe('Open')
    expect(changed).not.toHaveBeenCalled()
  })

  it.each([
    ['a fiscal year drop-down', '<label>Fiscal year <select name="fy"><option>2025</option><option>2026</option></select></label>', '2026'],
    ['a rows-per-page drop-down', '<select aria-label="Rows per page"><option>10</option><option>50</option></select>', '50'],
    ['a drop-down in a search form', '<form action="/search"><select name="type"><option>All</option><option>Grants</option></select></form>', 'Grants'],
    ['a drop-down in a filter panel', '<div id="filters"><select name="status"><option>Open</option><option>Closed</option></select></div>', 'Closed'],
  ])('chooses in %s', (_name, html, option) => {
    const el = field(html) as HTMLSelectElement
    expect(selectRef(1, option)).toMatchObject({ ok: true, selected: option })
    expect(el.value).toBe(option)
  })
})

describe('reading and finding numbered controls', () => {
  it('describes a public embedded form without reading it or forwarding a signed URL', () => {
    document.body.innerHTML = '<iframe title="Directory search" src="https://directory.example/search"></iframe><iframe title="Private view" src="https://private.example/p?ticket=secret"></iframe>'
    for (const frame of document.querySelectorAll('iframe')) {
      Object.defineProperty(frame, 'contentDocument', { get: () => null })
    }
    const page = readPage('', 20000)
    expect(page.unread_frames).toBe(2)
    expect(page.text).toContain('Embedded page "Directory search" (not read): https://directory.example/search')
    expect(page.text).not.toContain('private.example')
  })

  it('distinguishes the browser PDF viewer from a page containing an attachment', () => {
    document.body.innerHTML = '<embed type="application/pdf">'
    expect(readPage('', 20000).pdf_viewer).toBe(true)
    document.body.insertAdjacentHTML('afterbegin', '<p>Ordinary page with an attached file</p>')
    expect(readPage('', 20000).pdf_viewer).toBeUndefined()
  })

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
