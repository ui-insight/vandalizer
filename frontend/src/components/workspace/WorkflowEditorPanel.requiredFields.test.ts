import { describe, expect, it } from 'vitest'
import { requiredFieldMessage } from './WorkflowEditorPanel'

// An Add Website step could be saved with an empty URL and then "ran"
// successfully, feeding the next step nothing. The modal now refuses the
// save; these pin what counts as missing.
describe('requiredFieldMessage', () => {
  it('blocks an Add Website step with no URL', () => {
    expect(requiredFieldMessage('AddWebsite', {})).toMatch(/URL/)
    expect(requiredFieldMessage('AddWebsite', { url: '' })).toMatch(/URL/)
    expect(requiredFieldMessage('AddWebsite', { url: '   ' })).toMatch(/URL/)
  })

  it('allows an Add Website step with a URL', () => {
    expect(requiredFieldMessage('AddWebsite', { url: 'https://example.com' })).toBeNull()
  })

  it('blocks an API step with no URL', () => {
    expect(requiredFieldMessage('APINode', { url: '' })).toMatch(/URL/)
    expect(requiredFieldMessage('APINode', { url: 'https://api.example.com' })).toBeNull()
  })

  it('does not gate steps that have no URL field', () => {
    expect(requiredFieldMessage('Prompt', {})).toBeNull()
    expect(requiredFieldMessage('ResearchNode', { url: '' })).toBeNull()
  })
})

describe('requiredFieldMessage — Form Filler', () => {
  it('blocks a PDF-form template with no document chosen', () => {
    expect(requiredFieldMessage('FormFiller', { template_source: 'pdf' })).toMatch(/fillable PDF/)
    expect(requiredFieldMessage('FormFiller', { template_source: 'pdf', template_document_uuid: 'T' })).toBeNull()
  })

  it('blocks an empty text template (default source)', () => {
    expect(requiredFieldMessage('FormFiller', {})).toMatch(/template text/)
    expect(requiredFieldMessage('FormFiller', { template: '  ' })).toMatch(/template text/)
    expect(requiredFieldMessage('FormFiller', { template: 'Hi {{name}}' })).toBeNull()
  })
})
