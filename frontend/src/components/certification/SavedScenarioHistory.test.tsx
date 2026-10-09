import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import type { ScenarioDefinition, ScenarioHistoryList, ScenarioHistoryResult } from '../../types/certification'
import { SavedScenarioHistory } from './SavedScenarioHistory'
vi.mock('../../api/certification', () => ({ getSavedScenarioHistory: vi.fn(), getSavedScenarioHistoryResult: vi.fn() }))
const id = 'a'.repeat(32), bank = 'b'.repeat(64)
const definition: ScenarioDefinition = { module_id: 'ai_literacy', bank_id: 'original', bank_sha256: bank, revision: 1, questions: [{ id: 'source', prompt: 'Should you trust an unsupported answer?', choices: [{ id: 'verify', text: 'Check the source first' }] }] }
const list: ScenarioHistoryList = { enrollment_id: 'old-course', module_id: definition.module_id, bank_sha256: bank, read_only: true, older_attempts_available: false, attempts: [{ attempt_id: id, submitted_at: '2026-10-01T12:00:00Z', passed: false }] }
const result: ScenarioHistoryResult = { enrollment_id: 'old-course', module_id: definition.module_id, bank_sha256: bank, attempt_id: id, read_only: true, credit_awarded: false, assessment_kind: 'scenario_recognition', submitted_at: '2026-10-01T12:00:00Z', passed: false,
  questions: [{ id: 'source', prompt: definition.questions[0].prompt, chosen_answer: null, passed: false, feedback: '<script>Choose an answer for this required case.</script>' }] }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.getSavedScenarioHistory).mockResolvedValue(list); vi.mocked(api.getSavedScenarioHistoryResult).mockResolvedValue(result) })
function mount() { return render(<SavedScenarioHistory enrollmentId="old-course" definition={definition} />) }
async function inspect() { const button = await screen.findByRole('button', { name: /Open scenario result 1/ }); await act(async () => { fireEvent.click(button) }) }
it('reads original feedback only on request, distinguishes unanswered cases and focuses the saved result', async () => {
  mount(); await screen.findByRole('button', { name: /Open scenario result 1/ })
  expect(api.getSavedScenarioHistoryResult).not.toHaveBeenCalled()
  await inspect(); expect(await screen.findByRole('region', { name: 'Original scenario result' })).toHaveFocus()
  expect(screen.getByText('Your recorded choice: No answer recorded')).toBeInTheDocument()
  expect(screen.getByText('<script>Choose an answer for this required case.</script>')).toBeInTheDocument()
  expect(document.querySelector('script')).toBeNull()
  expect(screen.getByText(/No module credit awarded/)).toBeInTheDocument()
  expect(api.getSavedScenarioHistoryResult).toHaveBeenCalledWith('old-course', definition.module_id, id)
})
it.each(['owner', 'bank', 'credit', 'prompt', 'reference'])('rejects a mismatched %s saved result', async mismatch => {
  const wrong = structuredClone(result)
  if (mismatch === 'owner') wrong.enrollment_id = 'foreign'
  if (mismatch === 'bank') wrong.bank_sha256 = 'c'.repeat(64)
  if (mismatch === 'credit') Object.assign(wrong, { credit_awarded: true })
  if (mismatch === 'prompt') wrong.questions[0].prompt = 'Different requirements'
  if (mismatch === 'reference') wrong.attempt_id = 'd'.repeat(32)
  vi.mocked(api.getSavedScenarioHistoryResult).mockResolvedValue(wrong)
  mount(); await inspect(); expect(await screen.findByRole('alert')).toHaveTextContent('original course')
  expect(screen.queryByRole('region', { name: 'Original scenario result' })).not.toBeInTheDocument()
})
it('rejects a mismatched list and keeps full-reference recovery available', async () => {
  vi.mocked(api.getSavedScenarioHistory).mockResolvedValue({ ...list, enrollment_id: 'foreign' })
  mount(); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: /Open scenario result 1/ })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Full scenario reference'), { target: { value: id } })
  fireEvent.submit(screen.getByRole('button', { name: 'Open saved scenario result' }).closest('form')!)
  expect(await screen.findByRole('region', { name: 'Original scenario result' })).toBeInTheDocument()
})
it('clears a previous result on lookup failure and supports a read-only retry', async () => {
  mount(); await inspect(); await screen.findByRole('region', { name: 'Original scenario result' })
  vi.mocked(api.getSavedScenarioHistoryResult).mockRejectedValueOnce(new Error('Unavailable'))
  await inspect(); await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Original scenario result' })).not.toBeInTheDocument()
  await inspect(); await screen.findByRole('region', { name: 'Original scenario result' })
  expect(api.getSavedScenarioHistoryResult).toHaveBeenCalledTimes(3)
})
it('ignores late results after reloading history', async () => {
  let finish!: (value: ScenarioHistoryResult) => void
  vi.mocked(api.getSavedScenarioHistoryResult).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  mount(); await inspect()
  fireEvent.click(screen.getByRole('button', { name: 'Reload scenario history' }))
  await screen.findByRole('button', { name: /Open scenario result 1/ })
  await act(async () => finish(result))
  expect(screen.queryByRole('region', { name: 'Original scenario result' })).not.toBeInTheDocument()
})
it('explains an empty result history and recovers a failed listing', async () => {
  vi.mocked(api.getSavedScenarioHistory).mockRejectedValueOnce(new Error('Offline'))
  mount(); await screen.findByRole('alert')
  vi.mocked(api.getSavedScenarioHistory).mockResolvedValue({ ...list, attempts: [] })
  fireEvent.click(screen.getByRole('button', { name: 'Reload scenario history' }))
  expect(await screen.findByText('No saved scenario submissions are available for this module yet.')).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})
it('shows older-reference guidance without loading an older result automatically', async () => {
  vi.mocked(api.getSavedScenarioHistory).mockResolvedValue({ ...list, older_attempts_available: true })
  mount(); expect(await screen.findByText(/50 most recent submissions/)).toBeInTheDocument()
  expect(api.getSavedScenarioHistoryResult).not.toHaveBeenCalled()
})
