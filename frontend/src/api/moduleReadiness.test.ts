import { expect, it, vi } from 'vitest'
import { apiFetch } from './client'
import { getModuleReadiness } from './moduleReadiness'
vi.mock('./client', () => ({ apiFetch: vi.fn().mockResolvedValue({}) }))
it('uses GET with only exact explicit receipt identities, and omits empty selections', async () => {
  await getModuleReadiness('owner / cohort', 'module/one', { review: 'a'.repeat(32), scenario: 'b'.repeat(32) })
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/module%2Fone/readiness?enrollment_id=owner+%2F+cohort&review_attempt_id=' + 'a'.repeat(32) + '&scenario_attempt_id=' + 'b'.repeat(32))
  await getModuleReadiness('owner', 'module', {})
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/module/readiness?enrollment_id=owner')
})
