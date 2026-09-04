/**
 * The File toggle is the fix the ticket was about: it used to be offered on
 * document existence alone and then rendered `{"detail":"File not found"}`.
 * Nothing pinned the gating, so neither the 404 it fixes nor the regression it
 * introduced (a slow or failed detail call silently removing a file that
 * renders fine) had a test.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { KBSourceInspectorModal } from './KBSourceInspectorModal'
import type { KnowledgeBaseSource } from '../../types/knowledge'

vi.mock('../../api/knowledge', () => ({
  getKBSource: vi.fn(),
  setKBSourceReference: vi.fn(),
}))
// The viewer fetches the file itself; this suite is about whether the toggle
// is offered, not about rendering a PDF in jsdom.
vi.mock('../files/DocumentViewer', () => ({
  DocumentViewer: () => <div data-testid="doc-viewer" />,
}))

import { getKBSource } from '../../api/knowledge'

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
