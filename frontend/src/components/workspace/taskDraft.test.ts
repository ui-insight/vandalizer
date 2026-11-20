import { describe, expect, it, vi } from 'vitest'
import { isTaskDraft, newTaskDraft, saveTaskEdit } from './taskDraft'

// Support ticket: picking a task type saved an empty task at once; X left it
// in the step. A new task is now a draft until its details are saved.
describe('new workflow task drafts', () => {
  it('picking a type saves nothing: the task is a draft of its step', () => {
    const draft = newTaskDraft('step-1', 'Prompt')
    expect(draft).toEqual({ id: '', name: 'Prompt', data: {}, draftStepId: 'step-1' })
    expect(isTaskDraft(draft)).toBe(true)
    expect(newTaskDraft('step-1', 'KnowledgeBaseQuery').data).toEqual({ mode: 'answer' })
  })

  it('Save creates the draft in its step with the details filled in', async () => {
    const api = { addTask: vi.fn().mockResolvedValue({ id: 't1' }), updateTask: vi.fn() }
    await saveTaskEdit(newTaskDraft('step-1', 'Prompt'), { prompt: 'Summarize' }, api)
    expect(api.addTask).toHaveBeenCalledWith('step-1', { name: 'Prompt', data: { prompt: 'Summarize' } })
    expect(api.updateTask).not.toHaveBeenCalled()
  })

  it('Save on an existing task updates it', async () => {
    const api = { addTask: vi.fn(), updateTask: vi.fn().mockResolvedValue({}) }
    const task = { id: 't1', name: 'Prompt', data: {} }
    expect(isTaskDraft(task)).toBe(false)
    await saveTaskEdit(task, { prompt: 'Summarize' }, api)
    expect(api.updateTask).toHaveBeenCalledWith('t1', { data: { prompt: 'Summarize' } })
    expect(api.addTask).not.toHaveBeenCalled()
  })
})
