import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { LessonExtras } from './LessonContent'
import { practiceStorageKey } from '../../lib/certificationPractice'
import type { KnowledgeCheckData } from '../../types/certification'

const data: KnowledgeCheckData = { question: 'Which source?', options: [
  { text: 'Guess', correct: false, explanation: 'Inspect the source.' },
  { text: 'Assigned document', correct: true, explanation: 'Use its evidence.' },
] }
const scope = { userId: 'learner', enrollmentId: 'original-course', moduleId: 'foundations', lessonId: 'source-check', revision: 1 }
const key = practiceStorageKey(scope)!
beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

it('retains explicit attempts across lesson remounts without treating restored history as a new answer', () => {
  const view = render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  fireEvent.click(screen.getByRole('radio', { name: 'Guess' }))
  expect(localStorage.getItem(key)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  expect(JSON.parse(localStorage.getItem(key)!).attempts).toHaveLength(1)
  fireEvent.click(screen.getByRole('radio', { name: 'Assigned document' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  view.unmount()
  render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  expect(screen.getByText(/2 recent practice attempts saved on this browser/)).toBeInTheDocument()
  expect(screen.getByRole('status')).toBeEmptyDOMElement()
  expect(screen.getByRole('button', { name: 'Check answer' })).toBeDisabled()
  expect(screen.getByText(/does not award module credit/)).toBeInTheDocument()
  expect(JSON.parse(localStorage.getItem(key)!).attempts).toHaveLength(2)
})

it.each([{ userId: 'other' }, { enrollmentId: 'new-course' }, { lessonId: 'another' }, { revision: 2 }])('does not transfer practice between identities %j', change => {
  const view = render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  fireEvent.click(screen.getByRole('radio', { name: 'Assigned document' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  view.rerender(<LessonExtras knowledgeCheck={data} practiceScope={{ ...scope, ...change }} />)
  expect(screen.queryByText(/1 recent practice attempt/)).not.toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'Assigned document' })).not.toBeChecked()
})

it('rejects changed questions and malformed browser history without losing the lesson', () => {
  localStorage.setItem(key, JSON.stringify({ schema: 1, question: JSON.stringify(data), attempts: [{ choice: 9, savedAt: 'today' }] }))
  const view = render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  expect(screen.queryByText(/recent practice attempt/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('radio', { name: 'Guess' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  view.rerender(<LessonExtras knowledgeCheck={{ ...data, question: 'A corrected question?' }} practiceScope={scope} />)
  expect(screen.queryByText(/1 recent practice attempt/)).not.toBeInTheDocument()
})

it('keeps chat and panel histories consistent and clears only practice with useful focus', () => {
  render(<><section aria-label="chat"><LessonExtras knowledgeCheck={data} practiceScope={scope} /></section><section aria-label="panel"><LessonExtras knowledgeCheck={data} practiceScope={scope} /></section></>)
  const chat = within(screen.getByRole('region', { name: 'chat' }))
  const panel = within(screen.getByRole('region', { name: 'panel' }))
  localStorage.setItem('cert-lesson:learner', 'original-reading-place')
  fireEvent.click(chat.getByRole('radio', { name: 'Guess' }))
  fireEvent.click(chat.getByRole('button', { name: 'Check answer' }))
  expect(panel.getByText(/1 recent practice attempt/)).toBeInTheDocument()
  fireEvent.click(chat.getByText('Recent practice attempts'))
  fireEvent.click(chat.getByRole('button', { name: 'Clear saved practice' }))
  expect(chat.getByRole('radio', { name: 'Guess' })).toHaveFocus()
  expect(panel.queryByText(/1 recent practice attempt/)).not.toBeInTheDocument()
  expect(localStorage.getItem('cert-lesson:learner')).toBe('original-reading-place')
  expect(localStorage.getItem(key)).toBeNull()
})

it('responds to another tab clearing history and bounds history to twenty attempts', () => {
  localStorage.setItem(key, JSON.stringify({ schema: 1, question: JSON.stringify(data), attempts: Array.from({ length: 20 }, () => ({ choice: 0, savedAt: '2026-10-08T10:00:00Z' })) }))
  render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  fireEvent.click(screen.getByRole('radio', { name: 'Assigned document' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  expect(JSON.parse(localStorage.getItem(key)!).attempts).toHaveLength(20)
  expect(JSON.parse(localStorage.getItem(key)!).attempts.at(-1).choice).toBe(1)
  localStorage.removeItem(key)
  act(() => window.dispatchEvent(new StorageEvent('storage', { key })))
  expect(screen.queryByText(/20 recent practice attempts/)).not.toBeInTheDocument()
})

it('keeps feedback available and explains storage failure', () => {
  render(<LessonExtras knowledgeCheck={data} practiceScope={scope} />)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  fireEvent.click(screen.getByRole('radio', { name: 'Assigned document' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  expect(screen.getByRole('status')).toHaveTextContent('Correct.')
  expect(screen.getByRole('alert')).toHaveTextContent('could not be saved on this browser')
})
