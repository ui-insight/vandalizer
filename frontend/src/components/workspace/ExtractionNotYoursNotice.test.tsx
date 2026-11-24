import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { NotYoursNotice } from './ExtractionEditorPanel'

// #1164: a teammate's extraction can be run and copied, not changed.

it('says who can change the extraction and offers a copy', () => {
  const clone = vi.fn()
  render(<NotYoursNotice cloning={false} onClone={clone} />)
  expect(screen.getByRole('note')).toHaveTextContent('only its creator or a team admin can change it')
  fireEvent.click(screen.getByRole('button', { name: 'Make a copy to edit' }))
  expect(clone).toHaveBeenCalledOnce()
})

it('shows the copy in progress', () => {
  render(<NotYoursNotice cloning onClone={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Copying...' })).toBeDisabled()
})
