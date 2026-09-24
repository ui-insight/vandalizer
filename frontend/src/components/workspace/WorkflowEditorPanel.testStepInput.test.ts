import { describe, expect, it } from 'vitest'
import { describeTestStepInput } from './WorkflowEditorPanel'

const base = {
  taskName: 'Prompt',
  triggerType: 'manual',
  selectedDocUuids: [] as string[],
  fixedDocUuids: [] as string[],
}

const NEEDS_DOC = /Select a document in the library first/

describe('describeTestStepInput', () => {
  it('tests an API Node with no document selected (the ticket)', () => {
    expect(describeTestStepInput({ ...base, taskName: 'APINode' })).toEqual({
      docUuids: [], candidates: [], blockedHint: null,
    })
  })

  it('treats the other self-contained step types the same way', () => {
    for (const taskName of ['CrawlerNode', 'AddWebsite', 'KnowledgeBaseQuery']) {
      expect(describeTestStepInput({ ...base, taskName }).blockedHint).toBeNull()
    }
  })

  it('still asks a document-consuming step for a document, and says so', () => {
    const result = describeTestStepInput({ ...base, taskName: 'Extraction' })
    expect(result.docUuids).toEqual([])
    expect(result.blockedHint).toMatch(NEEDS_DOC)
  })

  it('lets fixed documents stand in for the selection, as a run does', () => {
    expect(describeTestStepInput({ ...base, fixedDocUuids: ['fixed-1'] })).toEqual({
      docUuids: ['fixed-1'], candidates: ['fixed-1'], blockedHint: null,
    })
  })

  it('prefers the selection over the fixed documents, and defaults to the first', () => {
    expect(describeTestStepInput({
      ...base, selectedDocUuids: ['sel-1', 'sel-2'], fixedDocUuids: ['fixed-1'],
    })).toEqual({ docUuids: ['sel-1'], candidates: ['sel-1', 'sel-2'], blockedHint: null })
  })

  it('tests the document picked under "Test against" — still just one', () => {
    expect(describeTestStepInput({
      ...base, selectedDocUuids: ['sel-1', 'sel-2', 'sel-3'], chosenDocUuid: 'sel-3',
    }).docUuids).toEqual(['sel-3'])
  })

  it('falls back to the first when the picked document is no longer a candidate', () => {
    expect(describeTestStepInput({
      ...base, selectedDocUuids: ['sel-1', 'sel-2'], chosenDocUuid: 'deselected',
    }).docUuids).toEqual(['sel-1'])
  })

  it('can pick among the fixed documents when nothing is selected', () => {
    expect(describeTestStepInput({
      ...base, fixedDocUuids: ['fixed-1', 'fixed-2'], chosenDocUuid: 'fixed-2',
    }).docUuids).toEqual(['fixed-2'])
  })

  it('never demands a document from a no-input workflow', () => {
    expect(describeTestStepInput({ ...base, triggerType: 'no_input' })).toEqual({
      docUuids: [], candidates: [], blockedHint: null,
    })
  })

  it('a text-input workflow can still be tested against a selected document', () => {
    expect(describeTestStepInput({ ...base, triggerType: 'text_input' }).blockedHint).toMatch(NEEDS_DOC)
    expect(describeTestStepInput({
      ...base, triggerType: 'text_input', selectedDocUuids: ['sel-1'],
    }).blockedHint).toBeNull()
  })
})
