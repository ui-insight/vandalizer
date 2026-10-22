import type { ContextType } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthContext } from '../../contexts/AuthContext'
import { SelfAssessment, MODULE_ASSESSMENTS } from './SelfAssessment'
import { reflectionDraftKey } from '../../lib/certificationReflectionDraft'

const submit = vi.fn()
const definition = MODULE_ASSESSMENTS.ai_literacy
const key = reflectionDraftKey('learner', 'ai_literacy', 'enrollment')!
function form({ userId = 'learner', enrollmentId = 'enrollment', existingAnswers, assessment = definition, submitting = false }: {
  userId?: string; enrollmentId?: string; existingAnswers?: Record<string, string>; assessment?: typeof definition; submitting?: boolean
} = {}) {
  const auth = { user: { user_id: userId } } as NonNullable<ContextType<typeof AuthContext>>
  return <AuthContext.Provider value={auth}><SelfAssessment moduleId="ai_literacy" enrollmentId={enrollmentId} definition={assessment} existingAnswers={existingAnswers} submitting={submitting} onSubmit={submit} /></AuthContext.Provider>
}
beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); submit.mockReset() })

it('restores only learner-selected choices after a remount and keeps the draft through an unconfirmed submission', () => {
  let view = render(form())
  for (const group of screen.getAllByRole('radiogroup')) fireEvent.click(within(group).getAllByRole('radio')[1])
  expect(screen.getByRole('status')).toHaveTextContent('Draft saved in this browser tab')
  const answers = JSON.parse(sessionStorage.getItem(key)!).answers
  fireEvent.click(screen.getByRole('button', { name: 'Submit Self-Assessment' }))
  expect(submit).toHaveBeenCalledExactlyOnceWith(answers)
  view.rerender(form({ submitting: true }))
  expect(screen.getByRole('button', { name: /Saving/ })).toBeDisabled()
  view.rerender(form()) // A failed or unauthenticated response leaves existingAnswers absent.
  view.unmount()
  view = render(form())
  expect(screen.getAllByRole('radio', { checked: true }).map(node => (node as HTMLInputElement).value)).toEqual(Object.values(answers))
  expect(sessionStorage.getItem(key)).not.toBeNull()
  expect(submit).toHaveBeenCalledTimes(1)
})

it.each([{ userId: 'different' }, { enrollmentId: 'different' }, { assessment: { ...definition, subtitle: 'A revised definition' } }])('does not silently transfer a draft across its binding %j', change => {
  const view = render(form())
  fireEvent.click(screen.getAllByRole('radio')[0])
  view.rerender(form(change))
  expect(screen.queryAllByRole('radio', { checked: true })).toHaveLength(0)
  expect(submit).not.toHaveBeenCalled()
})

it('uses confirmed server answers instead of stale draft choices and then removes the draft', () => {
  const view = render(form())
  fireEvent.click(screen.getAllByRole('radio')[0])
  const existingAnswers = Object.fromEntries(definition.questions.map(question => [question.key, question.options[1]]))
  view.rerender(form({ existingAnswers }))
  expect(screen.getByText('Reflection answers saved')).toBeInTheDocument()
  for (const answer of Object.values(existingAnswers)) expect(screen.getByText(answer)).toBeInTheDocument()
  expect(sessionStorage.getItem(key)).toBeNull()
  expect(submit).not.toHaveBeenCalled()
})

it('rejects malformed or unsupported stored choices without submitting them', () => {
  sessionStorage.setItem(key, JSON.stringify({ schema: 1, definition: JSON.stringify(definition), answers: { experience: 'Invented answer', unknown: 'Invented field' } }))
  render(form())
  expect(screen.queryAllByRole('radio', { checked: true })).toHaveLength(0)
  expect(screen.getByRole('button', { name: 'Submit Self-Assessment' })).toBeDisabled()
  expect(submit).not.toHaveBeenCalled()
})

it('keeps selected answers usable and announces blocked draft storage', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  render(form())
  for (const group of screen.getAllByRole('radiogroup')) fireEvent.click(within(group).getAllByRole('radio')[0])
  expect(screen.getByRole('alert')).toHaveTextContent('could not save your draft')
  fireEvent.click(screen.getByRole('button', { name: 'Submit Self-Assessment' }))
  expect(submit).toHaveBeenCalledTimes(1)
  expect(Object.keys(submit.mock.calls[0][0])).toHaveLength(3)
})
