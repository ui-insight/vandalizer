import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ExtractionNeedsFieldsNotice } from './ExtractionNeedsFieldsNotice'

// Support ticket: with no fields, "Validate & improve" could be started and
// failed a few seconds later with "No extraction fields defined". The tab now
// leads with this notice instead of the controls.
describe('ExtractionNeedsFieldsNotice', () => {
  it('tells the user to add fields and jumps to the Design tab', () => {
    const onAddFields = vi.fn()
    render(<ExtractionNeedsFieldsNotice onAddFields={onAddFields} />)
    expect(screen.getByRole('status')).toHaveTextContent('Add fields first')
    expect(screen.getByRole('status')).toHaveTextContent('Validate & improve')
    fireEvent.click(screen.getByRole('button', { name: /Add fields on the Design tab/ }))
    expect(onAddFields).toHaveBeenCalledTimes(1)
  })

  it('mentions saved test cases so they do not look lost', () => {
    render(<ExtractionNeedsFieldsNotice savedTestCaseCount={2} onAddFields={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('2 saved test cases will be ready to use as soon as a field exists')
    const { unmount } = render(<ExtractionNeedsFieldsNotice savedTestCaseCount={1} onAddFields={vi.fn()} />)
    expect(screen.getAllByRole('status')[1]).toHaveTextContent('1 saved test case will')
    unmount()
  })

  it('offers no action to a viewer who cannot manage the extraction', () => {
    render(<ExtractionNeedsFieldsNotice canManage={false} onAddFields={vi.fn()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('ask its owner to add fields')
  })
})
