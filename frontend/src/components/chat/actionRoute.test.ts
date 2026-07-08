import { describe, it, expect } from 'vitest'
import { routeActionClick } from './actionRoute'

describe('routeActionClick', () => {
  it('routes the two known actions to dedicated behavior', () => {
    expect(routeActionClick('start-cert', 'Start the Certification Program')).toEqual({ kind: 'cert' })
    expect(routeActionClick('upload-docs', 'Upload your documents')).toEqual({ kind: 'files' })
  })

  it('sends the label for any improvised action so it is not a dead button', () => {
    expect(routeActionClick('create-kb', 'Create Knowledge Base'))
      .toEqual({ kind: 'send', message: 'Create Knowledge Base' })
    expect(routeActionClick('build-workflow', '  Build Workflow  '))
      .toEqual({ kind: 'send', message: 'Build Workflow' })
    expect(routeActionClick('create-extraction-from-document', 'Create Extraction from Document'))
      .toEqual({ kind: 'send', message: 'Create Extraction from Document' })
  })

  it('does nothing for a labelless button or a missing action attribute', () => {
    expect(routeActionClick('create-kb', '   ')).toEqual({ kind: 'none' })
    expect(routeActionClick(null, 'whatever')).toEqual({ kind: 'none' })
  })
})
