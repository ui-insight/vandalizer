import { describe, it, expect } from 'vitest'
import {
  deriveStepInput,
  effectiveTaskInput,
  inputValuePatch,
  readInputValue,
  sameInputValue,
  taskOverridesStepInput,
  toggleSource,
} from './stepInputConfig'
import type { WorkflowStep, WorkflowTask } from '../../types/workflow'

const task = (id: string, data: Record<string, unknown>): WorkflowTask =>
  ({ id, name: 'Prompt', data })

const step = (data: Record<string, unknown>, tasks: WorkflowTask[]): WorkflowStep =>
  ({ id: 's1', name: 'Analyze', data, is_output: false, tasks })

describe('readInputValue', () => {
  it('reads the multi-select list', () => {
    expect(readInputValue({ input_sources: ['workflow_documents', 'step_input'] })).toEqual({
      sources: ['workflow_documents', 'step_input'],
      selectedDocUuid: '',
    })
  })

  it('falls back to the legacy single value', () => {
    expect(readInputValue({ input_source: 'select_document', selected_document_uuid: 'd1' })).toEqual({
      sources: ['select_document'],
      selectedDocUuid: 'd1',
    })
  })

  it('defaults to step_input when nothing is stored', () => {
    expect(readInputValue({}).sources).toEqual(['step_input'])
    expect(readInputValue(undefined).sources).toEqual(['step_input'])
  })

  it('drops values that are not real sources', () => {
    expect(readInputValue({ input_sources: ['nonsense', 'step_input'] }).sources).toEqual(['step_input'])
    expect(readInputValue({ input_sources: ['nonsense'] }).sources).toEqual(['step_input'])
  })
})

describe('inputValuePatch', () => {
  it('writes the list, the legacy mirror, and the document', () => {
    expect(inputValuePatch({ sources: ['select_document'], selectedDocUuid: 'd7' })).toEqual({
      input_sources: ['select_document'],
      input_source: 'select_document',
      selected_document_uuid: 'd7',
    })
  })

  it('clears the document when it is not one of the sources', () => {
    expect(inputValuePatch({ sources: ['step_input'], selectedDocUuid: 'd7' }).selected_document_uuid).toBe('')
  })
})

describe('toggleSource', () => {
  it('adds and removes', () => {
    expect(toggleSource(['step_input'], 'workflow_documents')).toEqual(['step_input', 'workflow_documents'])
    expect(toggleSource(['step_input', 'workflow_documents'], 'step_input')).toEqual(['workflow_documents'])
  })

  it('refuses to empty the selection', () => {
    // A step with no source has no input at all — keep the last one checked.
    expect(toggleSource(['step_input'], 'step_input')).toEqual(['step_input'])
  })
})

describe('sameInputValue', () => {
  it('ignores a stale document when select_document is off', () => {
    expect(sameInputValue(
      { sources: ['step_input'], selectedDocUuid: 'd1' },
      { sources: ['step_input'], selectedDocUuid: '' },
    )).toBe(true)
  })

  it('separates different orders', () => {
    expect(sameInputValue(
      { sources: ['step_input', 'workflow_documents'], selectedDocUuid: '' },
      { sources: ['workflow_documents', 'step_input'], selectedDocUuid: '' },
    )).toBe(false)
  })
})

describe('deriveStepInput', () => {
  it('uses the step when the step has been configured', () => {
    const s = step({ input_sources: ['workflow_documents'] }, [
      task('t1', { input_sources: ['step_input'] }),
    ])
    const d = deriveStepInput(s)
    expect(d.value.sources).toEqual(['workflow_documents'])
    expect(d.fromStep).toBe(true)
    expect(d.divergentTasks).toEqual([])
  })

  it('seeds from the tasks when the step has nothing stored', () => {
    const s = step({}, [
      task('t1', { input_sources: ['workflow_documents'] }),
      task('t2', { input_sources: ['workflow_documents'] }),
    ])
    const d = deriveStepInput(s)
    expect(d.value.sources).toEqual(['workflow_documents'])
    expect(d.fromStep).toBe(false)
    expect(d.divergentTasks).toEqual([])
  })

  it('reports the odd tasks out when the tasks disagree', () => {
    const s = step({}, [
      task('t1', { input_sources: ['workflow_documents'] }),
      task('t2', { input_sources: ['step_input'] }),
      task('t3', { input_sources: ['workflow_documents'] }),
    ])
    const d = deriveStepInput(s)
    expect(d.value.sources).toEqual(['workflow_documents'])
    expect(d.divergentTasks.map(t => t.id)).toEqual(['t2'])
  })

  it('ignores tasks that never configured input when looking for disagreement', () => {
    const s = step({}, [
      task('t1', { input_sources: ['workflow_documents'] }),
      task('t2', { prompt: 'hi' }),
    ])
    expect(deriveStepInput(s).divergentTasks).toEqual([])
  })

  it('defaults to step_input for a brand new step', () => {
    const d = deriveStepInput(step({}, []))
    expect(d.value.sources).toEqual(['step_input'])
    expect(d.fromStep).toBe(false)
  })
})

describe('effectiveTaskInput', () => {
  it('gives a task the step’s input', () => {
    const t = task('t1', { input_sources: ['step_input'] })
    const s = step({ input_sources: ['workflow_documents'] }, [t])
    expect(effectiveTaskInput(s, t).sources).toEqual(['workflow_documents'])
  })

  it('honors the advanced per-task override', () => {
    const t = task('t1', { override_step_input: true, input_sources: ['select_document'], selected_document_uuid: 'd2' })
    const s = step({ input_sources: ['workflow_documents'] }, [t])
    expect(effectiveTaskInput(s, t)).toEqual({ sources: ['select_document'], selectedDocUuid: 'd2' })
    expect(taskOverridesStepInput(t)).toBe(true)
  })

  it('falls back to the task on a workflow authored before the move', () => {
    const t = task('t1', { input_sources: ['workflow_documents'] })
    const s = step({}, [t])
    expect(effectiveTaskInput(s, t).sources).toEqual(['workflow_documents'])
  })
})
