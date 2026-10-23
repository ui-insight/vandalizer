import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WorkflowSourcesPanel } from './WorkflowEditorPanel'

describe('WorkflowSourcesPanel', () => {
  it('opens a web result at its URL and keeps a knowledge-base passage as a label', () => {
    render(<WorkflowSourcesPanel sources={[
      { document_title: 'PAPPG 24-1', url: 'https://nsf.gov/pappg', content_preview: 'Page limit: 15 pages.' },
      { document_title: 'Award terms.pdf', page: 3, chunk_id: 'c1' },
    ]} />)
    fireEvent.click(screen.getByRole('button', { name: /Sources \(2\)/ }))

    const link = screen.getByRole('link', { name: /PAPPG 24-1/ })
    expect(link).toHaveAttribute('href', 'https://nsf.gov/pappg')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(screen.getByText(/Award terms\.pdf/)).not.toHaveAttribute('href')
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })
})
