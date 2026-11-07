import type { ContextType, ReactNode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthContext } from '../../contexts/AuthContext'
import { BatchRunActions } from './BatchForms'
import { OutputRunActions } from './OutputWorkflowForms'
import { ValidationRunActions } from './ValidationForms'
import { GovernanceRunActions } from './GovernanceForms'
import type { BatchRun } from '../../types/batchAssessment'
import type { OutputRun } from '../../types/outputWorkflow'
import type { ValidationRun } from '../../types/validationSuite'
import type { GovernanceRun } from '../../types/governanceAssessment'

// Only public run fields consumed by these scope controls; no provider or saved approval.
const original = { enrollment_id: 'source-course', manifest_sha256: 'a'.repeat(64), run_id: 'b'.repeat(32), plan_sha256: 'c'.repeat(64), case_sha256: 'd'.repeat(64),
  scope_decision_id: null as string | null, scope_decision_sha256: null as string | null, scope_decision: null, can_save_scope: true, can_execute: false, can_finalize: false,
  phase: 'pilot', input_snapshot: { case: { questions: [{ id: 'pilot_choice', prompt: 'Explain the scope of this pilot.' }] } }, approval_question: { prompt: 'Inspect this exact capstone extraction.' } }
const send = vi.fn()
const controls = [
  ['batch', (run: typeof original) => <BatchRunActions run={run as unknown as BatchRun} locked={false} send={send} />],
  ['output', (run: typeof original) => <OutputRunActions run={run as unknown as OutputRun} locked={false} send={send} onInspect={vi.fn()} />],
  ['validation', (run: typeof original) => <ValidationRunActions run={run as unknown as ValidationRun} locked={false} send={send} />],
  ['governance', (run: typeof original) => <GovernanceRunActions run={run as unknown as GovernanceRun} locked={false} send={send} />],
] as const
function auth(child: ReactNode) {
  return <AuthContext.Provider value={{ user: { user_id: 'scope-learner' } } as NonNullable<ContextType<typeof AuthContext>>}>{child}</AuthContext.Provider>
}
beforeEach(() => { sessionStorage.clear(); send.mockReset() })

it.each(controls)('%s restores only an unsubmitted choice, without enabling execution or saving it', (_, control) => {
  const view = render(auth(control(original)))
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My original explanation of the exact bounded scope.' } })
  view.unmount()
  render(auth(control(original)))
  expect(screen.getByRole('combobox')).toHaveValue('approve')
  expect(screen.getByRole('textbox')).toHaveValue('My original explanation of the exact bounded scope.')
  expect(screen.getByRole('status')).toHaveTextContent('Use the save action to submit it')
  expect(screen.getAllByRole('button')).toHaveLength(1)
  expect(send).not.toHaveBeenCalled()
  fireEvent.submit(screen.getByRole('form'))
  expect(send).toHaveBeenCalledTimes(1)
  expect(send.mock.calls[0][0]).toMatchObject({ action: 'scope', body: { run_id: original.run_id, plan_sha256: original.plan_sha256, choice: 'approve', reason: 'My original explanation of the exact bounded scope.' } })
})

it.each(controls)('%s starts a fresh draft when the saved approval changes', (_, control) => {
  const view = render(auth(control(original)))
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Earlier unsaved approval explanation.' } })
  view.rerender(auth(control({ ...original, scope_decision_id: 'e'.repeat(32), scope_decision_sha256: 'f'.repeat(64) })))
  expect(screen.getByRole('combobox')).toHaveValue('hold')
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(send).not.toHaveBeenCalled()
  view.rerender(auth(control(original)))
  expect(screen.getByRole('textbox')).toHaveValue('Earlier unsaved approval explanation.')
})

it.each(controls)('%s never carries an approval draft into a different prepared plan', (_, control) => {
  const view = render(auth(control(original)))
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Approval applies to the original plan only.' } })
  view.rerender(auth(control({ ...original, plan_sha256: 'e'.repeat(64) })))
  expect(screen.getByRole('combobox')).toHaveValue('hold')
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(send).not.toHaveBeenCalled()
})
