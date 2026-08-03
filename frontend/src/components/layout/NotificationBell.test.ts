import { describe, expect, it } from 'vitest'
import { parseNotificationLink } from './NotificationBell'

describe('parseNotificationLink', () => {
  it('keeps a plain path as-is', () => {
    expect(parseNotificationLink('/verification')).toEqual({
      to: '/verification',
      search: {},
    })
  })

  it('splits workspace deep-links into path and search', () => {
    // Failure notifications route into the workspace by query param; passing
    // the whole string as `to` would drop them.
    expect(parseNotificationLink('/?workflow=wf-123')).toEqual({
      to: '/',
      search: { workflow: 'wf-123' },
    })
  })

  it('handles multiple params', () => {
    expect(parseNotificationLink('/?mode=automations&automation=a-1')).toEqual({
      to: '/',
      search: { mode: 'automations', automation: 'a-1' },
    })
  })

  it('decodes encoded values', () => {
    expect(parseNotificationLink('/?extraction=a%20b').search).toEqual({
      extraction: 'a b',
    })
  })

  it('falls back to root for a bare query string', () => {
    expect(parseNotificationLink('?tab=library')).toEqual({
      to: '/',
      search: { tab: 'library' },
    })
  })
})
