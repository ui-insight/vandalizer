import { describe, it, expect } from 'vitest'
import type { WorkflowStep } from '../../types/workflow'
import { describeUnfinishedSteps, findUnfinishedSteps, promptTaskIsEmpty } from './workflowStepIssues'

function step(id: string, name: string, tasks: Array<{ id: string; name: string; data?: Record<string, unknown> }>): WorkflowStep {
  return { id, name, data: {}, is_output: false, tasks: tasks.map(t => ({ id: t.id, name: t.name, data: t.data ?? {} })) }
}

describe('promptTaskIsEmpty', () => {
  it('is true for a Prompt task with no prompt key, an empty prompt, or whitespace', () => {
    expect(promptTaskIsEmpty('Prompt', {})).toBe(true)
    expect(promptTaskIsEmpty('Prompt', undefined)).toBe(true)
    expect(promptTaskIsEmpty('Prompt', { prompt: '' })).toBe(true)
    expect(promptTaskIsEmpty('Prompt', { prompt: '  \n\t ' })).toBe(true)
    expect(promptTaskIsEmpty('Prompt', { prompt: 42 })).toBe(true)
  })

  it('is false once there is prompt text', () => {
    expect(promptTaskIsEmpty('Prompt', { prompt: 'Summarize this' })).toBe(false)
  })

  it('is false when a saved Library prompt is linked, even with no inline text', () => {
    expect(promptTaskIsEmpty('Prompt', { saved_prompt_uuid: 'abc' })).toBe(false)
    expect(promptTaskIsEmpty('Prompt', { saved_prompt_uuid: '', prompt: '' })).toBe(true)
  })

  it('never flags other task types', () => {
    expect(promptTaskIsEmpty('Formatter', {})).toBe(false)
    expect(promptTaskIsEmpty('Extraction', { prompt: '' })).toBe(false)
  })
})

describe('findUnfinishedSteps', () => {
  it('numbers steps the way the canvas does — hidden empty Document steps are skipped', () => {
    const steps = [
      step('doc', 'Document', []),
      step('s1', 'Fetch', [{ id: 't1', name: 'AddWebsite', data: { url: 'https://x' } }]),
      step('s2', 'Summarize', [{ id: 't2', name: 'Prompt', data: { name: 'Summarize', prompt: '' } }]),
    ]
    const issues = findUnfinishedSteps(steps)
    expect(issues).toHaveLength(1)
    expect(issues[0]).toMatchObject({ stepId: 's2', stepNumber: 2, taskId: 't2', taskLabel: 'Summarize' })
  })

  it('falls back to the task type as the label and reports every empty Prompt task', () => {
    const steps = [
      step('s1', 'A', [{ id: 't1', name: 'Prompt', data: {} }, { id: 't2', name: 'Prompt', data: { prompt: 'ok' } }]),
      step('s2', 'B', [{ id: 't3', name: 'Prompt', data: { prompt: ' ' } }]),
    ]
    const issues = findUnfinishedSteps(steps)
    expect(issues.map(i => i.taskId)).toEqual(['t1', 't3'])
    expect(issues[0].taskLabel).toBe('Prompt')
  })

  it('returns nothing for a workflow whose prompts are all filled or linked', () => {
    const steps = [
      step('s1', 'A', [{ id: 't1', name: 'Prompt', data: { prompt: 'x' } }]),
      step('s2', 'B', [{ id: 't2', name: 'Prompt', data: { saved_prompt_uuid: 'lib-1' } }]),
    ]
    expect(findUnfinishedSteps(steps)).toEqual([])
    expect(describeUnfinishedSteps([])).toBeNull()
  })
})

describe('describeUnfinishedSteps', () => {
  it('names the first offending step and counts the rest', () => {
    const steps = [
      step('s1', 'A', [{ id: 't1', name: 'Prompt', data: { name: 'Draft memo' } }]),
      step('s2', 'B', [{ id: 't2', name: 'Prompt', data: {} }]),
    ]
    const text = describeUnfinishedSteps(findUnfinishedSteps(steps))
    expect(text).toBe('Step 1 "Draft memo" has no prompt (and 1 more) — open the step and add instructions before running')
  })
})
