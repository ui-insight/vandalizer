import { describe, expect, it } from 'vitest'
import { describeRunInput, describeSelectionCount } from './WorkflowEditorPanel'

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

  it('counts ticked folders as a selection and says what the run will use', () => {
    expect(describeRunInput({ ...base, selectedFolderCount: 2 })).toEqual({
      missing: false, hint: 'Will run on the documents in the 2 selected folders, including subfolders',
    })
    expect(describeRunInput({ ...base, selectedFolderCount: 1, selectedCount: 1, hasProject: true }).hint)
      .toBe('Will run on the documents in the selected folder, including subfolders')
    expect(describeRunInput({ ...base, triggerType: 'no_input', selectedFolderCount: 2 })).toEqual({ missing: false, hint: null })
  })
})

describe('describeSelectionCount', () => {
  it('names folders alongside documents', () => {
    expect(describeSelectionCount(0, 0)).toBe('0 selected')
    expect(describeSelectionCount(3, 0)).toBe('3 selected')
    expect(describeSelectionCount(0, 2)).toBe('2 folders selected')
    expect(describeSelectionCount(1, 1)).toBe('1 folder, 1 document selected')
    expect(describeSelectionCount(2, 3)).toBe('3 folders, 2 documents selected')
  })
})
