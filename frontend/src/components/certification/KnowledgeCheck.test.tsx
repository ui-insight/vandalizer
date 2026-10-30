import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { KnowledgeCheck } from './KnowledgeCheck'
it('associates the answer group with its question and supports correction without awarding credit', () => {
  render(<KnowledgeCheck data={{ question: 'Which source should you use?', options: [
    { text: 'A guess', correct: false, explanation: 'Inspect the source document.' },
    { text: 'The assigned document', correct: true, explanation: 'The document supports this answer.' },
  ] }} />)
  expect(screen.getByRole('radiogroup', { name: 'Which source should you use?' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check answer' })).toBeDisabled()
  fireEvent.click(screen.getByRole('radio', { name: 'A guess' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  expect(screen.getByRole('status')).toHaveTextContent('Not quite. Inspect the source document.')
  fireEvent.click(screen.getByRole('radio', { name: 'The assigned document' }))
  expect(screen.getByRole('status')).toBeEmptyDOMElement()
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  expect(screen.getByRole('status')).toHaveTextContent('Correct. The document supports this answer.')
  expect(screen.getByText(/does not award module credit/)).toBeInTheDocument()
})
