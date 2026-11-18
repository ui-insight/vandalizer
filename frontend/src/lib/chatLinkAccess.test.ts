import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { describeLinkFailure, describePartialLink, isAccessRefusal } from './chatLinkAccess'

describe('isAccessRefusal', () => {
  it('is true for the server saying no', () => {
    expect(isAccessRefusal(new ApiError(404, 'Knowledge base not found'))).toBe(true)
    expect(isAccessRefusal(new ApiError(403, 'Forbidden'))).toBe(true)
  })
  it('is false for a 403 that is about the session, not the item', () => {
    expect(isAccessRefusal(new ApiError(403, 'DEMO_EXPIRED'))).toBe(false)
    expect(isAccessRefusal(new ApiError(403, 'CSRF validation failed (reloading)'))).toBe(false)
  })
  it('is false when no answer came back', () => {
    expect(isAccessRefusal(new ApiError(0, 'Network error'))).toBe(false)
    expect(isAccessRefusal(new ApiError(500, 'Server error'))).toBe(false)
    expect(isAccessRefusal(new TypeError('Load failed'))).toBe(false)
  })
})

describe('describeLinkFailure', () => {
  const none = { kbs: 0, docs: 0, folders: 0, loadFailed: false }
  it('names the knowledge base for a single knowledge base link', () => {
    const text = describeLinkFailure({ ...none, kbs: 1 })
    expect(text).toContain('knowledge base in this link isn’t shared with you')
    expect(text).toContain('this chat won’t use it')
  })
  it('names a document or a folder', () => {
    expect(describeLinkFailure({ ...none, docs: 1 })).toContain('The document in this link')
    expect(describeLinkFailure({ ...none, folders: 1 })).toContain('The folder in this link')
  })
  it('speaks of items when the link carried several', () => {
    expect(describeLinkFailure({ ...none, kbs: 1, docs: 2 })).toContain('None of the items')
  })
  it('does not blame sharing when the request itself failed', () => {
    const text = describeLinkFailure({ ...none, kbs: 1, loadFailed: true })
    expect(text).not.toContain('shared')
    expect(text).toContain('open the link again')
  })
})

describe('describePartialLink', () => {
  it('says the rest are not shared when the server refused them', () => {
    expect(describePartialLink({ attached: 1, requested: 2, loadFailed: false }))
      .toBe('1 of 2 items from this link are attached. The other one isn’t shared with you. Ask the person who sent it to share it.')
    expect(describePartialLink({ attached: 1, requested: 3, loadFailed: false }))
      .toContain('The other 2 aren’t shared with you. Ask the person who sent it to share them.')
  })
  it('does not blame sharing when a request failed', () => {
    const text = describePartialLink({ attached: 1, requested: 2, loadFailed: true })
    expect(text).toContain('1 of 2 items from this link are attached.')
    expect(text).not.toContain('shared')
    expect(text).toContain('open the link again')
  })
})
