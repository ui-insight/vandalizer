import { describe, it, expect } from 'vitest'
import { describeSchedule, isScheduleComplete, scheduleConfigPayload, defaultScheduleConfig, formatRunTime } from './schedule'

const base = { ...defaultScheduleConfig(), timezone: 'UTC' }

describe('schedule helpers', () => {
  it('describes each frequency in plain words', () => {
    expect(describeSchedule({ ...base, frequency: 'daily', time: '17:30' })).toBe('Daily at 17:30')
    expect(describeSchedule({ ...base, frequency: 'weekly', weekday: 4, time: '08:00' })).toBe('Every Friday at 08:00')
    expect(describeSchedule({ ...base, frequency: 'monthly', day_of_month: 2, time: '08:00' })).toBe('Monthly on the 2nd at 08:00')
    expect(describeSchedule({ ...base, frequency: 'monthly', day_of_month: 11, time: '08:00' })).toBe('Monthly on the 11th at 08:00')
  })

  it('is complete only with something to run on', () => {
    expect(isScheduleComplete({ ...base, source: 'folder' })).toBe(false)
    expect(isScheduleComplete({ ...base, source: 'folder', folder_id: 'f1' })).toBe(true)
    expect(isScheduleComplete({ ...base, source: 'documents', document_uuids: [] })).toBe(false)
    expect(isScheduleComplete({ ...base, source: 'documents', document_uuids: ['d1'] })).toBe(true)
  })

  it('sends only the fields for the chosen frequency and source', () => {
    const folder = scheduleConfigPayload({ ...base, frequency: 'daily', folder_id: 'f1', only_new: true, document_uuids: ['stale'] })
    expect(folder).toEqual({ frequency: 'daily', time: '09:00', timezone: 'UTC', source: 'folder', folder_id: 'f1', only_new: true })
    const docs = scheduleConfigPayload({ ...base, frequency: 'monthly', day_of_month: 5, source: 'documents', document_uuids: ['d1'], document_titles: { d1: 'A.pdf' }, folder_id: 'f1' })
    expect(docs).toEqual({
      frequency: 'monthly', day_of_month: 5, time: '09:00', timezone: 'UTC', source: 'documents',
      document_uuids: ['d1'], document_titles: { d1: 'A.pdf' },
    })
  })

  it('formats a run time in the schedule zone', () => {
    const text = formatRunTime('2026-09-28T15:00:00+00:00', 'America/Boise')
    expect(text).toMatch(/9:00/)
    expect(text).toMatch(/MDT/)
  })
})
