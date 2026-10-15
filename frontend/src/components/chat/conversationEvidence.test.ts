import { describe, expect, it } from 'vitest'
import { conversationEvidence } from './conversationEvidence'
describe('conversation export evidence', () => {
  it('retains approximate pages, quoted evidence and source names without upgrading support', () => {
    const text = conversationEvidence({ role: 'assistant', content: 'Budget is 200.', interruption: 'connection', unsupported_figures: ['200'], citations: [{ document_title: 'Budget.pdf', document_uuid: 'doc-1', page: 2, page_end: 3, page_approximate: true, kb_title: 'Sponsor rules', kb_uuid: 'kb-1', url: 'https://example.test/rules', content_preview: 'Budget is 150.', source_reference: 'Section 4' }] })
    for (const value of ['partial output', 'Unconfirmed figures: 200', 'p. ~2–3', 'Budget is 150.', 'Budget.pdf', 'Knowledge base: Sponsor rules', 'https://example.test/rules', 'Section 4']) expect(text).toContain(value)
    // A source with a name is named, not identified.
    expect(text).not.toContain('doc-1')
    expect(text).not.toContain('kb-1')
  })
  it('falls back to the ID only for a source that has no name', () => {
    const text = conversationEvidence({ role: 'assistant', content: 'x', citations: [{ document_title: '', document_uuid: 'doc-9', content_preview: 'p' }] })
    expect(text).toContain('Document ID: doc-9')
  })
  it('names the recorded turn scope and leaves unnamed items counted, not identified', () => {
    // Support ticket: every message ended "Scope when sent: Document IDs: None
    // selected / Folder IDs: None selected / …".
    const text = conversationEvidence(
      { role: 'user', content: 'Question', request_scope: { documents: ['doc-1', 'doc-2'], folders: [], knowledgeBases: ['kb-1'], project: 'project-1' } },
      { 'doc-1': 'Budget.xlsx', 'kb-1': 'Subaward Policies', 'project-1': 'Grant X' },
    )
    expect(text).toContain('Selected when sent:')
    expect(text).toContain('Documents: Budget.xlsx and 1 other')
    expect(text).toContain('Knowledge bases: Subaward Policies')
    expect(text).toContain('Project: Grant X')
    expect(text).not.toMatch(/Folders|None selected|doc-2|ID/)
  })
  it('says nothing about scope when nothing was selected or none was recorded', () => {
    expect(conversationEvidence({ role: 'user', content: 'Question', request_scope: { documents: [], folders: [], knowledgeBases: [] } })).toBe('')
    expect(conversationEvidence({ role: 'user', content: 'Old question' })).toBe('')
    expect(conversationEvidence({ role: 'user', content: 'Old question', source_documents: [{ uuid: 'old-1', title: 'Deleted document' }, { truncated: 2 }] })).toContain('2 additional documents were not recorded.')
  })
  it('does not invent citation evidence for an ungrounded answer', () => {
    expect(conversationEvidence({ role: 'assistant', content: 'An answer' })).toBe('No source references were recorded for this answer.')
  })
})
