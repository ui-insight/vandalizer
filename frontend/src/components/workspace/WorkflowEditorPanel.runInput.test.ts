import { describe, expect, it } from 'vitest'
import { describeRunInput } from './WorkflowEditorPanel'

const base = { triggerType: 'manual', selectedCount: 0, fixedCount: 0, hasProject: false, textInput: '' }

describe('describeRunInput', () => {
  it('blocks a manual run with nothing selected and nothing fixed', () => {
    expect(describeRunInput(base)).toEqual({ missing: true, hint: 'Select a document to run this workflow' })
  })

  it('lets fixed documents stand in for the selection', () => {
    expect(describeRunInput({ ...base, fixedCount: 1 })).toEqual({
      missing: false, hint: 'Will run on its 1 fixed document — select more to add to them',
    })
    expect(describeRunInput({ ...base, fixedCount: 3 }).hint).toMatch(/3 fixed documents/)
  })

  it('a selection needs no hint, project fallback keeps its hint', () => {
    expect(describeRunInput({ ...base, selectedCount: 2, fixedCount: 1 })).toEqual({ missing: false, hint: null })
    expect(describeRunInput({ ...base, hasProject: true })).toEqual({ missing: false, hint: 'Will run on all files in this project' })
  })

  it('text and no-input modes are unchanged', () => {
    expect(describeRunInput({ ...base, triggerType: 'text_input' })).toEqual({ missing: true, hint: null })
    expect(describeRunInput({ ...base, triggerType: 'text_input', textInput: 'hi' }).missing).toBe(false)
    expect(describeRunInput({ ...base, triggerType: 'no_input' })).toEqual({ missing: false, hint: null })
  })
})
