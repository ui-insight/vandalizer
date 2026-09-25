import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { WebSourceRefreshBar, oldestRetrieval } from './WebSourceRefreshBar'
import { refreshKBWebSources, updateKnowledgeBase } from '../../api/knowledge'
import type { KnowledgeBaseSource } from '../../types/knowledge'

vi.mock('../../api/knowledge', () => ({
  refreshKBWebSources: vi.fn(),
  updateKnowledgeBase: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

const web = (uuid: string, retrieved: string | null) => ({
  uuid, source_type: 'url', url: `https://example.gov/${uuid}`, status: 'ready',
  currency: retrieved ? { last_retrieved_at: retrieved } : null,
}) as unknown as KnowledgeBaseSource
const doc = { uuid: 'd', source_type: 'document', status: 'ready' } as unknown as KnowledgeBaseSource

describe('oldestRetrieval', () => {
  it('is the oldest web retrieval, "never" if one was never retrieved, null with no web sources', () => {
    expect(oldestRetrieval([web('a', '2026-09-01T00:00:00Z'), web('b', '2026-06-24T09:00:00Z'), doc])).toBe('2026-06-24T09:00:00Z')
    expect(oldestRetrieval([web('a', '2026-09-01T00:00:00Z'), web('b', null)])).toBe('never')
    expect(oldestRetrieval([doc])).toBeNull()
  })
})

describe('WebSourceRefreshBar', () => {
  const props = { kbUuid: 'kb-1', interval: null, canManage: true, onChanged: vi.fn(), onError: vi.fn() }

  it('renders nothing for a KB with no web sources', () => {
    const { container } = render(<WebSourceRefreshBar {...props} sources={[doc]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('says how current the web sources are and refreshes them all', async () => {
    vi.mocked(refreshKBWebSources).mockResolvedValue({ ok: true, queued: 2, in_progress: 0 })
    const onChanged = vi.fn()
    render(<WebSourceRefreshBar {...props} onChanged={onChanged} sources={[web('a', '2026-09-01T00:00:00Z'), web('b', '2026-06-24T09:00:00Z')]} />)
    expect(screen.getByTestId('web-source-refresh-bar').textContent).toMatch(/2 web sources · oldest retrieved Jun 24, 2026/)
    fireEvent.click(screen.getByRole('button', { name: /Refresh all/ }))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.stringMatching(/Re-fetching 2 web pages/)))
    expect(refreshKBWebSources).toHaveBeenCalledWith('kb-1')
  })

  it('saves the auto-refresh interval', async () => {
    vi.mocked(updateKnowledgeBase).mockResolvedValue({ ok: true })
    const onChanged = vi.fn()
    render(<WebSourceRefreshBar {...props} onChanged={onChanged} sources={[web('a', null)]} />)
    fireEvent.change(screen.getByLabelText('Refresh web sources automatically'), { target: { value: 'weekly' } })
    await waitFor(() => expect(updateKnowledgeBase).toHaveBeenCalledWith('kb-1', { url_refresh_interval: 'weekly' }))
    expect(onChanged).toHaveBeenCalledWith('Web sources will refresh weekly')
  })

  it('is read-only for someone who cannot manage the KB', () => {
    render(<WebSourceRefreshBar {...props} canManage={false} interval="monthly" sources={[web('a', null)]} />)
    expect(screen.queryByRole('button', { name: /Refresh all/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Refresh web sources automatically')).toBeDisabled()
    expect(screen.getByLabelText('Refresh web sources automatically')).toHaveValue('monthly')
  })
})
