import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SourcedStatement, SourcingLink, WorkflowSourcing } from '../../types/workflow'
import { CitedMarkdown, renderCitedMarkdown, renderCitedText } from './CitedMarkdown'
import { SourcedJson, SourcingSummary, structuredLeafSpan, textLeafSpan, useSourcing } from './Sourcing'
import { codePointIndex, stripMarks, viewerTerm, withSentinels } from './sourcingSpans'

// The workspace a source opens documents through; null outside a workspace.
const workspace = vi.hoisted(() => ({
  current: null as { setWorkspaceMode: (mode: string) => void; viewDocument: (...args: unknown[]) => void } | null,
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useOptionalWorkspace: () => workspace.current }))

const NOA: SourcingLink = {
  kind: 'document', document_uuid: 'noa', document_title: 'NoA.pdf', page: 2,
  quote: 'Recipient: Southern Utah University',
  excerpt: 'Award details\nRecipient: Southern Utah University\nPeriod',
  quote_start: 14, quote_end: 49,
}
const KB: SourcingLink = {
  kind: 'kb', kb_title: 'OMB Uniform Guidance', document_title: 'Subpart E', label: 'OMB UG — Subpart E · part 10',
  quote: 'a prudent person', excerpt: 'does not exceed what a prudent person would incur', quote_start: 22, quote_end: 38,
}

function spansOf(html: string): Array<[string, string]> {
  const div = document.createElement('div')
  div.innerHTML = html
  return Array.from(div.querySelectorAll('.src-u, .src-x')).map(el => [el.className, el.textContent ?? ''])
}

describe('marks', () => {
  it('count code points the way the backend does', () => {
    const at = codePointIndex('🤖 ok')
    expect([at(0), at(1), at(2)]).toEqual([0, 2, 3])
    expect(codePointIndex('plain')(3)).toBe(3)
  })

  it('hand the viewer the words the page shows, without an extractor\'s formatting marks', () => {
    expect(viewerTerm('All grants require the FFAR** **funding request.')).toBe('All grants require the FFAR funding request.')
    expect(viewerTerm('P.I. Biosketch</u>: three-page limit')).toBe('P.I. Biosketch: three-page limit')
    expect(viewerTerm('Due:\nMarch 9, 2022 *(see note)*')).toBe('Due: March 9, 2022 (see note)')
    expect(viewerTerm('file_name stays')).toBe('file_name stays')
  })

  it('wrap each span and nothing else; overlapping spans are dropped, not nested', () => {
    const text = 'Alpha beta. Gamma delta.'
    const rows: SourcedStatement[] = [{ s: 0, e: 11 }, { s: 12, e: 24 }, { s: 5, e: 15 }]
    const marked = withSentinels(text, rows)
    expect(stripMarks(marked)).toBe(text)
    expect(marked.length).toBe(text.length + 4)
  })
})

describe('renderCitedMarkdown with sourcing', () => {
  const md = '**Recipient:** Southern Utah University\n\n| Event | Date |\n|---|---|\n| Due | **July 13, 2022** |\n'
  const rows: SourcedStatement[] = [
    { s: 15, e: 39, src: 0 },                       // "Southern Utah University"
    { s: md.indexOf('July'), e: md.indexOf('2022') + 4 },
  ]

  it('underlines a traced statement where it is rendered and leaves the text as written', () => {
    const html = renderCitedMarkdown(md, [], { rows, sources: [NOA], showUntraced: false })
    expect(spansOf(html)).toEqual([['src-u', 'Southern Utah University'], ['src-x', 'July 13, 2022']])
    const div = document.createElement('div')
    div.innerHTML = html
    // The rendered text is identical to rendering without sourcing.
    const plain = document.createElement('div')
    plain.innerHTML = renderCitedMarkdown(md, [])
    expect(div.textContent).toBe(plain.textContent)
    expect(html).not.toMatch(/[-]/)
    // The cell's statement sits inside its <strong>, which survives.
    expect(div.querySelector('td strong .src-x, td .src-x')).not.toBeNull()
  })

  it('a statement that crosses emphasis becomes one span per text run', () => {
    const text = 'The award is **final** today.'
    const html = renderCitedMarkdown(text, [], { rows: [{ s: 0, e: text.length, src: 0 }], sources: [NOA], showUntraced: false })
    expect(spansOf(html).map(([, t]) => t).join('')).toBe('The award is final today.')
    expect(html).toContain('<strong>')
  })

  it('says why an untraced statement is plain only while the reviewer asks', () => {
    const r: SourcedStatement[] = [{ s: 0, e: 4, t: 'verdict' }]
    expect(renderCitedText('Pass', [], { rows: r, sources: [], showUntraced: false })).not.toContain('title=')
    expect(renderCitedText('Pass', [], { rows: r, sources: [], showUntraced: true })).toContain('A judgment drawn from the facts')
  })

  it('never leaves a mark inside a link it lands in', () => {
    const text = 'See https://example.org'
    const html = renderCitedMarkdown(text, [], { rows: [{ s: 0, e: text.length, src: 0 }], sources: [NOA], showUntraced: false })
    expect(html).not.toMatch(/[-]|%EE%80/i)
  })
})

describe('the source popover', () => {
  beforeEach(() => { workspace.current = null })

  function Harness({ sourcing }: { sourcing: WorkflowSourcing }) {
    const src = useSourcing(sourcing, 'final')
    return (
      <>
        {src.summary}
        <CitedMarkdown markdown="**Recipient:** Southern Utah University. Costs are reasonable." sources={[]} sourcing={src.text} />
        {src.popover}
      </>
    )
  }
  const sourcing: WorkflowSourcing = {
    status: 'done', sources: [NOA],
    targets: { final: { format: 'text', statements: [{ s: 15, e: 40, src: 0 }, { s: 41, e: 62 }], summary: { statements: 2, traced: 1 } } },
  }

  it('shows the passage with the supporting words marked, and opens the document at that page', () => {
    const viewDocument = vi.fn()
    const setWorkspaceMode = vi.fn()
    workspace.current = { setWorkspaceMode, viewDocument }
    render(<Harness sourcing={sourcing} />)
    expect(screen.getByText('1 of 2 statements traced to a source')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Southern Utah University/ }))
    const dialog = screen.getByRole('dialog', { name: 'Source: NoA.pdf · p. 2' })
    expect(dialog.querySelector('mark')?.textContent).toBe('Recipient: Southern Utah University')
    fireEvent.click(screen.getByRole('button', { name: 'Open at p. 2' }))
    expect(setWorkspaceMode).toHaveBeenCalledWith('files')
    expect(viewDocument).toHaveBeenCalledWith('noa', 'NoA.pdf', {
      terms: ['Recipient: Southern Utah University'], page: 2, pageApproximate: false,
    })
  })

  it('the reviewer toggle tints what was not traced', () => {
    const { container } = render(<Harness sourcing={sourcing} />)
    expect(container.querySelector('.show-untraced')).toBeNull()
    fireEvent.click(screen.getByLabelText('Highlight untraced'))
    expect(container.querySelector('.show-untraced .src-x')?.textContent).toBe('Costs are reasonable.')
  })

  it('a knowledge-base source shows its passage and no document to open', () => {
    workspace.current = { setWorkspaceMode: vi.fn(), viewDocument: vi.fn() }
    render(<Harness sourcing={{ ...sourcing, sources: [KB] }} />)
    fireEvent.click(screen.getByRole('button', { name: /Southern Utah University/ }))
    expect(screen.getByText('OMB Uniform Guidance')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Open/ })).toBeNull()
  })
})

describe('SourcingSummary', () => {
  it('says the trace is running, failed, or how much it found', () => {
    const { rerender, container } = render(
      <SourcingSummary sourcing={{ status: 'running' }} target="final" showUntraced={false} onToggle={() => {}} />,
    )
    expect(container.textContent).toContain('Tracing sources…')
    rerender(<SourcingSummary sourcing={{ status: 'failed', error: 'Sources could not be traced for this run.' }} target="final" showUntraced={false} onToggle={() => {}} />)
    expect(container.textContent).toBe('Sources could not be traced for this run.')
    rerender(<SourcingSummary sourcing={null} target="final" showUntraced={false} onToggle={() => {}} />)
    expect(container.textContent).toBe('')
  })
})

describe('SourcedJson', () => {
  const value = {
    award_number: 'L24AC00293-00',
    amount: 1240,
    notes: ['The award is "final". It runs to 2029.', '🤖 bot'],
    nested: { empty: {}, list: [], flag: true, none: null },
  }

  it('prints exactly what JSON.stringify prints, with the statements marked', () => {
    const rows: SourcedStatement[] = [
      { p: ['award_number'], s: 0, e: 13, src: 0 },
      { p: ['amount'] },
      { p: ['notes', 0], s: 0, e: 21, src: 0 },
      { p: ['notes', 0], s: 22, e: 38 },
      { p: ['notes', 1], s: 2, e: 5 },                // after a two-unit emoji
      { p: ['nested', 'flag'], t: 'verdict' },
    ]
    const { container } = render(
      <SourcedJson value={value} rows={rows} sources={[NOA]} showUntraced={false} onOpen={() => {}} leafSpan={structuredLeafSpan} />,
    )
    const pre = container.querySelector('pre') as HTMLElement
    expect(pre.textContent).toBe(JSON.stringify(value, null, 2))
    const marked = Array.from(pre.querySelectorAll('.src-u, .src-x')).map(el => el.textContent)
    expect(marked).toEqual(['L24AC00293-00', '1240', 'The award is \\"final\\".', 'It runs to 2029.', 'bot', 'true'])
  })

  it('places statements of JSON written as text by their leaf offsets', () => {
    const rows: SourcedStatement[] = [{ p: ['note'], s: 10, e: 24, ls: 0, le: 14, src: 0 }]
    const onOpen = vi.fn()
    render(
      <SourcedJson value={{ note: 'Due July 13th.' }} rows={rows} sources={[NOA]} showUntraced={false} onOpen={onOpen} leafSpan={textLeafSpan} />,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledWith(0, expect.any(HTMLElement))
  })
})
