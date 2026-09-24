/**
 * The File toggle is the fix the ticket was about: it used to be offered on
 * document existence alone and then rendered `{"detail":"File not found"}`.
 * Nothing pinned the gating, so neither the 404 it fixes nor the regression it
 * introduced (a slow or failed detail call silently removing a file that
 * renders fine) had a test.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { KBSourceInspectorModal } from './KBSourceInspectorModal'
import type { KnowledgeBaseSource } from '../../types/knowledge'

vi.mock('../../api/knowledge', () => ({
  getKBSource: vi.fn(),
  setKBSourceReference: vi.fn(),
  setKBSourceAmends: vi.fn(),
}))
// The viewer fetches the file itself; this suite is about whether the toggle
// is offered, not about rendering a PDF in jsdom.
vi.mock('../files/DocumentViewer', () => ({
  DocumentViewer: () => <div data-testid="doc-viewer" />,
}))

import { getKBSource, setKBSourceAmends } from '../../api/knowledge'

const source = {
  uuid: 'src-1',
  source_type: 'document',
  document_uuid: 'doc-1',
  document_title: 'FY26 Budget.pdf',
  document_exists: true,
} as unknown as KnowledgeBaseSource

function renderModal() {
  return render(
    <KBSourceInspectorModal kbUuid="kb-1" source={source} onClose={() => {}} />,
  )
}

const detail = (over: Record<string, unknown>) => ({
  uuid: 'src-1',
  source_type: 'document',
  document_uuid: 'doc-1',
  document_exists: true,
  content: 'indexed text',
  ...over,
})

describe('KBSourceInspectorModal — File view gating', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers the File view when the server says the file is available', async () => {
    vi.mocked(getKBSource).mockResolvedValue(detail({ document_file: 'available' }) as never)
    renderModal()
    expect(await screen.findByRole('button', { name: 'File' })).toBeInTheDocument()
  })

  it.each([
    ['no_access', /isn’t shared with you/i],
    ['missing', /missing from storage/i],
  ])('hides it and says why when the file is %s', async (status, note) => {
    vi.mocked(getKBSource).mockResolvedValue(detail({ document_file: status }) as never)
    renderModal()

    await waitFor(() => expect(screen.getByText(note)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'File' })).not.toBeInTheDocument()
  })

  it('still offers the File view when the detail request fails', async () => {
    // The regression this guards: hiding on an unknown status turns a slow or
    // failed detail call into "this file does not exist", which is the same
    // wrong answer as the 404 it replaced, pointing the other way.
    vi.mocked(getKBSource).mockRejectedValue(new Error('boom'))
    renderModal()
    expect(await screen.findByRole('button', { name: 'File' })).toBeInTheDocument()
  })
})


describe('KBSourceInspectorModal — Amends', () => {
  // Support ticket: a PAPPG supplement only reached answers when the user named
  // its file. The KB owner marks it as amending Chapter IV instead.
  const supplement = {
    uuid: 'src-supp', source_type: 'document', document_uuid: 'doc-supp',
    document_title: 'NSF_PAPPG_24-1_Supplement_1.pdf', document_exists: true, amends_source_uuids: [],
  } as unknown as KnowledgeBaseSource
  const chapterIV = {
    uuid: 'src-ch4', source_type: 'document', document_title: 'NSF_PAPPG_24-1_Chapter_IV.pdf',
  } as unknown as KnowledgeBaseSource
  const faq = { uuid: 'src-faq', source_type: 'url', url_title: 'NSF FAQ' } as unknown as KnowledgeBaseSource

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getKBSource).mockResolvedValue(detail({ uuid: 'src-supp' }) as never)
  })

  it('saves the picked source and shows it as a chip', async () => {
    vi.mocked(setKBSourceAmends).mockResolvedValue({ amends_source_uuids: ['src-ch4'] } as never)
    const onUpdated = vi.fn()
    render(
      <KBSourceInspectorModal
        kbUuid="kb-1" source={supplement} otherSources={[supplement, chapterIV, faq]}
        onClose={() => {}} onUpdated={onUpdated}
      />,
    )

    const select = screen.getByLabelText('Amends')
    // The source itself is never offered.
    expect(screen.queryByRole('option', { name: 'NSF_PAPPG_24-1_Supplement_1.pdf' })).toBeNull()
    fireEvent.change(select, { target: { value: 'src-ch4' } })

    await waitFor(() => expect(setKBSourceAmends).toHaveBeenCalledWith('kb-1', 'src-supp', ['src-ch4']))
    expect(await screen.findByRole('button', { name: 'Stop amending NSF_PAPPG_24-1_Chapter_IV.pdf' })).toBeInTheDocument()
    expect(onUpdated).toHaveBeenCalled()
  })

  it('removing a chip saves the shorter list', async () => {
    vi.mocked(setKBSourceAmends).mockResolvedValue({ amends_source_uuids: [] } as never)
    const linked = { ...supplement, amends_source_uuids: ['src-ch4'] } as KnowledgeBaseSource
    render(
      <KBSourceInspectorModal kbUuid="kb-1" source={linked} otherSources={[linked, chapterIV]} onClose={() => {}} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Stop amending NSF_PAPPG_24-1_Chapter_IV.pdf' }))

    await waitFor(() => expect(setKBSourceAmends).toHaveBeenCalledWith('kb-1', 'src-supp', []))
  })

  it('puts the chip back when the save fails', async () => {
    vi.mocked(setKBSourceAmends).mockRejectedValue(new Error('Not a source of this knowledge base: src-ch4'))
    render(
      <KBSourceInspectorModal kbUuid="kb-1" source={supplement} otherSources={[supplement, chapterIV]} onClose={() => {}} />,
    )

    fireEvent.change(screen.getByLabelText('Amends'), { target: { value: 'src-ch4' } })

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Stop amending/ })).toBeNull(),
    )
  })

  it('is not shown when the KB has no other source to amend', () => {
    render(<KBSourceInspectorModal kbUuid="kb-1" source={supplement} otherSources={[supplement]} onClose={() => {}} />)
    expect(screen.queryByLabelText('Amends')).toBeNull()
  })
})
