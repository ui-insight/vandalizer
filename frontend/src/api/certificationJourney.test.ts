import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { observeCertificationJourney } from './certificationJourney'
vi.mock('./client', () => ({ getCsrfToken: () => 'csrf-test' }))
const fetchMock = vi.fn()
beforeEach(() => { fetchMock.mockReset().mockResolvedValue({ status: 403 }); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => vi.unstubAllGlobals())

it('sends only the allowed identity and event, with authentication and CSRF', () => {
  const source = { enrollment_id: 'a'.repeat(32), manifest_sha256: 'b'.repeat(64), answers: 'PRIVATE', user_id: 'PRIVATE' }
  observeCertificationJourney('position_save_failed', source)
  expect(fetchMock).toHaveBeenCalledOnce()
  const [path, options] = fetchMock.mock.calls[0]
  expect(path).toBe('/api/certification/journey-events')
  expect(options.credentials).toBe('include')
  expect(options.headers['X-CSRF-Token']).toBe('csrf-test')
  expect(JSON.parse(options.body)).toEqual({ event_id: expect.stringMatching(/^[a-f0-9]{32}$/), event: 'position_save_failed',
    enrollment_id: source.enrollment_id, manifest_sha256: source.manifest_sha256 })
  expect(options.body).not.toContain('PRIVATE')
})
it('drops success observations without identity while preserving unattributed load failures', () => {
  observeCertificationJourney('saved_lesson_displayed')
  observeCertificationJourney('bridge_assessment_requested', { enrollment_id: 'a'.repeat(32) })
  expect(fetchMock).not.toHaveBeenCalled()
  observeCertificationJourney('initial_progress_load_failed')
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ event_id: expect.any(String), event: 'initial_progress_load_failed' })
})
it('does not throw, retry, read errors or trigger recovery on telemetry failure', async () => {
  const json = vi.fn(() => { throw new Error('Must not interpret optional telemetry as an actionable course error') })
  fetchMock.mockResolvedValueOnce({ status: 403, json }).mockRejectedValueOnce(new Error('PRIVATE network failure'))
  expect(() => observeCertificationJourney('initial_progress_load_failed')).not.toThrow()
  expect(() => observeCertificationJourney('initial_progress_load_failed')).not.toThrow()
  await Promise.resolve(); await Promise.resolve()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(json).not.toHaveBeenCalled()
})
