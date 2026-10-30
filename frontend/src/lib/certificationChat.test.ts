import { expect, it } from 'vitest'
import type { CertificationProgress } from '../types/certification'
import { certificationChatEntry, CONTINUE_CERTIFICATION_MESSAGE, REVIEW_CERTIFICATION_MESSAGE, START_CERTIFICATION_MESSAGE } from './certificationChat'

const progress = (value: Record<string, unknown>) => value as unknown as CertificationProgress

it('starts the course when nothing is saved', () => {
  expect(certificationChatEntry(null, null)).toMatchObject({ message: START_CERTIFICATION_MESSAGE, certified: false })
  expect(certificationChatEntry(progress({ modules: {} }), null).label).toBe('Start the certification course')
})

it('continues with the selected course denominator once work is saved', () => {
  const entry = certificationChatEntry(progress({ modules: { a: { completed: true }, b: {} }, module_ids: ['a', 'b'], modules_total: 2 }), null)
  expect(entry).toEqual({ label: 'Continue certification (1/2)', message: CONTINUE_CERTIFICATION_MESSAGE, certified: false })
})

it('reviews the course in chat once certified', () => {
  expect(certificationChatEntry(progress({ certified: true, modules: {} }), null)).toMatchObject({ message: REVIEW_CERTIFICATION_MESSAGE, certified: true })
})
