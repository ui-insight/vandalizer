import { describe, expect, it } from 'vitest'
import { conversationEvidence } from './conversationEvidence'
describe('conversation export evidence', () => {
  it('retains approximate pages, quoted evidence and original identifiers without upgrading support', () => {
    const text = conversationEvidence({ role: 'assistant', content: 'Budget is 200.', interruption: 'connection', unsupported_figures: ['200'], citations: [{ document_title: 'Budget.pdf', document_uuid: 'doc-1', page: 2, page_end: 3, page_approximate: true, kb_title: 'Sponsor rules', kb_uuid: 'kb-1', url: 'https://example.test/rules', content_preview: 'Budget is 150.', source_reference: 'Section 4' }] })
    for (const value of ['partial output', 'Unconfirmed figures: 200', 'p. ~2–3', 'Budget is 150.', 'doc-1', 'kb-1', 'https://example.test/rules', 'Section 4']) expect(text).toContain(value)
  })
  it('uses the recorded turn scope and discloses missing historical scope', () => {
    expect(conversationEvidence({ role: 'user', content: 'Question', request_scope: { documents: ['doc-before-switch'], folders: ['folder-1'], knowledgeBases: ['kb-1'], project: 'project-1' } })).toContain('Document IDs: doc-before-switch')
    expect(conversationEvidence({ role: 'user', content: 'Old question', source_documents: [{ uuid: 'old-1', title: 'Deleted document' }, { truncated: 2 }] })).toContain('2 additional documents were not recorded.')
    expect(conversationEvidence({ role: 'user', content: 'Old question' })).toContain('Full request scope was not recorded')
  })
  it('does not invent citation evidence for an ungrounded answer', () => {
    expect(conversationEvidence({ role: 'assistant', content: 'An answer' })).toBe('No source references were recorded for this answer.')
  })
})
