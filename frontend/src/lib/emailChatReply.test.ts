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
  it.each([
    'Total = 2 * 3 * 4 hours',
    'Rate is a ** b ** c',
    'Edit __init__.py and my_file_name.txt',
    'Use snake_case and other_names here',
    '5 * 3 (see note) * 2.',
  ])('leaves arithmetic and file names alone: %s', (text) => {
    expect(markdownToPlain(text)).toBe(text)
  })
  it('keeps a bullet whose text holds arithmetic', () => {
    expect(markdownToPlain('* Cost: 2 * 3\n* _Total:_ 6')).toBe('- Cost: 2 * 3\n- Total: 6')
  })
  it('keeps what is inside a code fence exactly', () => {
    expect(markdownToPlain('Run:\n```python\n# comment\nx = a ** b ** c\n```\n**Done**'))
      .toBe('Run:\n\n# comment\nx = a ** b ** c\n\nDone')
  })
  it('drops chat buttons and the address of a link into Vandalizer', () => {
    expect(markdownToPlain('See [Award notice](doc:3f2a-11) for terms.\n\n[ACTION:upload-docs]Upload your documents[/ACTION]'))
      .toBe('See Award notice for terms.')
  })
})

describe('emailDraftFromReply', () => {
  it('uses a Subject line the reply wrote and starts the email after it', () => {
    const draft = emailDraftFromReply('Here is a draft:\n\n**Subject:** Award highlights for subaward 123\n\nHello Dr. Park,\n\nThe award is $148,500.')
    expect(draft.subject).toBe('Award highlights for subaward 123')
    expect(draft.body).toBe('Hello Dr. Park,\n\nThe award is $148,500.')
  })
  it('keeps every line of a memo that has a Subject among its headers', () => {
    const memo = 'Summary of the memo:\n\n**To:** Dr. Park\n**From:** OSP\n**Subject:** Award modification 3\n**Date:** May 1\n\nThe period is extended.'
    const draft = emailDraftFromReply(memo)
    expect(draft.subject).toBe('Award modification 3')
    expect(draft.body).toBe('Summary of the memo:\n\nTo: Dr. Park\nFrom: OSP\nSubject: Award modification 3\nDate: May 1\n\nThe period is extended.')
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
  it('encodes punctuation and survives half an emoji', () => {
    expect(mailtoUrl('A & B #1', '50% + tax')).toBe('mailto:?subject=A%20%26%20B%20%231&body=50%25%20%2B%20tax')
    expect(mailtoUrl('', 'cut \uD83D')).toBe('mailto:?body=cut%20%EF%BF%BD')
  })
})
