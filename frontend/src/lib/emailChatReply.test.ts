import { describe, expect, it } from 'vitest'
import { emailDraftFromReply, mailtoUrl, markdownToPlain } from './emailChatReply'

describe('markdownToPlain', () => {
  it('keeps the words and drops the markup', () => {
    const text = '## Award highlights\n\n**Amount:** $148,500\n* Start: `09/01/2025`\n* See [the terms](https://example.org/t)\n\n---\n\n_Thanks_'
    expect(markdownToPlain(text)).toBe('Award highlights\n\nAmount: $148,500\n- Start: 09/01/2025\n- See the terms (https://example.org/t)\n\nThanks')
  })
  it('leaves ordinary text alone', () => {
    expect(markdownToPlain('Budget is 2 * 3 = 6, file_name_here.pdf')).toBe('Budget is 2 * 3 = 6, file_name_here.pdf')
  })
})

describe('emailDraftFromReply', () => {
  it('uses a Subject line the reply wrote and starts the email after it', () => {
    const draft = emailDraftFromReply('Here is a draft:\n\n**Subject:** Award highlights for subaward 123\n\nHello Dr. Park,\n\nThe award is $148,500.')
    expect(draft.subject).toBe('Award highlights for subaward 123')
    expect(draft.body).toBe('Hello Dr. Park,\n\nThe award is $148,500.')
  })
  it('leaves the subject empty when the reply has none', () => {
    expect(emailDraftFromReply('The award is $148,500.')).toEqual({ subject: '', body: 'The award is $148,500.' })
  })
})

describe('mailtoUrl', () => {
  it('has no recipient and carries line breaks an email app understands', () => {
    expect(mailtoUrl('Hi', 'a\nb')).toBe('mailto:?subject=Hi&body=a%0D%0Ab')
    expect(mailtoUrl('', '')).toBe('mailto:')
  })
})
