import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'

const api = vi.hoisted(() => ({
  getSourceSuggestionsAvailable: vi.fn(),
  suggestSources: vi.fn(),
}))
vi.mock('../../api/knowledge', () => api)

// Feature request: describe a topic, approve suggested pages, instead of
// hunting down links. A checked suggestion joins the URL list, so it is added
// through the ordinary Add URLs submit.
describe('Find pages by topic', () => {
  beforeEach(() => {
    api.getSourceSuggestionsAvailable.mockReset()
    api.suggestSources.mockReset()
  })

  it('is hidden where web search is not configured', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: false })
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(api.getSourceSuggestionsAvailable).toHaveBeenCalledWith('kb-1'))
    expect(screen.queryByLabelText(/Find pages by topic/)).toBeNull()
  })

  it('adds checked suggestions to the URL list that Add submits', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: true })
    api.suggestSources.mockResolvedValue({
      available: true, queries: ['NSF proposal requirements'], already_in_kb: 2, error: null,
      suggestions: [
        { url: 'https://nsf.gov/pappg', title: 'PAPPG', snippet: '', host: 'nsf.gov', reason: 'The proposal guide.' },
        { url: 'https://nsf.gov/budget', title: 'Budget', snippet: 'Budget rules', host: 'nsf.gov', reason: null },
      ],
    })
    const onSubmit = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onClose={vi.fn()} />)

    const topic = await screen.findByLabelText(/Find pages by topic/)
    fireEvent.change(topic, { target: { value: 'NSF proposal requirements' } })
    fireEvent.click(screen.getByRole('button', { name: /Find pages/ }))

    expect(await screen.findByText('The proposal guide.')).toBeTruthy()
    expect(screen.getByText('Budget rules')).toBeTruthy()
    expect(screen.getByText(/2 more pages found are already in this knowledge base/)).toBeTruthy()
    expect(api.suggestSources).toHaveBeenCalledWith('kb-1', 'NSF proposal requirements')

    const textarea = screen.getByLabelText('URLs to add, one per line') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'https://example.com/mine' } })
    fireEvent.click(screen.getByLabelText('PAPPG'))
    fireEvent.click(screen.getByLabelText('Budget'))
    fireEvent.click(screen.getByLabelText('Budget'))
    expect(textarea.value).toBe('https://example.com/mine\nhttps://nsf.gov/pappg')

    fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
    expect(onSubmit).toHaveBeenCalledWith(['https://example.com/mine', 'https://nsf.gov/pappg'], false, 5, '')
  })

  it('shows the search error', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: true })
    api.suggestSources.mockRejectedValue(new Error('Web search failed: HTTP 401'))
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText(/Find pages by topic/), { target: { value: 'IRB rules' } })
    fireEvent.click(screen.getByRole('button', { name: /Find pages/ }))
    expect(await screen.findByText('Web search failed: HTTP 401')).toBeTruthy()
  })
})
