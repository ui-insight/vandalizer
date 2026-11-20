import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ toast: vi.fn(), mintWorkflow: vi.fn(), mintSet: vi.fn(), write: vi.fn() }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ toast: api.toast }) }))
vi.mock('../api/workflows', () => ({ mintWorkflowShareToken: api.mintWorkflow }))
vi.mock('../api/extractions', () => ({ mintSearchSetShareToken: api.mintSet }))
import { ApiError } from '../api/client'

import { buildShareUrl, useShareLink } from './shareLink'

beforeEach(() => {
  vi.clearAllMocks()
  api.write.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: api.write }, configurable: true })
})

const copied = () => new URL(api.write.mock.calls[0][0] as string)

describe('share links', () => {
  it('gives a Skill a link anyone signed in can open', async () => {
    api.mintSet.mockResolvedValue({ share_token: 'tok/en+1' })
    const { result } = renderHook(() => useShareLink())
    await result.current('extraction', 'skill-1', 'Award review')

    expect(api.mintSet).toHaveBeenCalledWith('skill-1')
    expect(copied().pathname).toBe('/shared')
    expect(copied().searchParams.get('item')).toBe('skill-1')
    expect(copied().searchParams.get('token')).toBe('tok/en+1')
    expect(api.toast).toHaveBeenCalledWith('“Award review” copied. Anyone signed in can open it.', 'success')
  })

  it.each([
    ['an extraction', 400], ['a Skill the person cannot edit', 404], ['a refused request', 403],
  ])('copies a plain link for %s and says who it works for', async (_what, status) => {
    api.mintSet.mockRejectedValue(new ApiError(status, 'refused'))
    const { result } = renderHook(() => useShareLink())
    await result.current('extraction', 'skill-1')

    expect(copied().pathname).toBe('/')
    expect(copied().search).toBe('?extraction=skill-1')
    expect(api.toast).toHaveBeenCalledWith('Link copied. It opens for people who already have access.', 'success')
  })

  it.each([new ApiError(500, 'boom'), new TypeError('Failed to fetch')])(
    'copies nothing when the link could not be made (%s)', async (failure) => {
      api.mintSet.mockRejectedValue(failure)
      const { result } = renderHook(() => useShareLink())
      await result.current('extraction', 'skill-1')

      expect(api.write).not.toHaveBeenCalled()
      expect(api.toast).toHaveBeenCalledWith('Could not generate share link.', 'error')
    })

  it('does not promise open access for a knowledge base link', async () => {
    const { result } = renderHook(() => useShareLink())
    await result.current('kb', 'kb-1', 'Uniform Guidance')

    expect(api.mintSet).not.toHaveBeenCalled()
    expect(copied().search).toBe('?kb=kb-1')
    expect(api.toast).toHaveBeenCalledWith('“Uniform Guidance” copied. It opens for people who already have access.', 'success')
  })

  it('keeps the workflow link as it was', async () => {
    api.mintWorkflow.mockResolvedValue({ share_token: 'wf-tok' })
    const { result } = renderHook(() => useShareLink())
    await result.current('workflow', 'wf-1')

    expect(copied().pathname).toBe('/')
    expect(copied().searchParams.get('workflow')).toBe('wf-1')
    expect(copied().searchParams.get('workflow_share_token')).toBe('wf-tok')
    expect(api.toast).toHaveBeenCalledWith('Link copied. Anyone signed in can open it.', 'success')

    api.write.mockClear(); api.toast.mockClear()
    api.mintWorkflow.mockRejectedValue(new Error('no'))
    await result.current('workflow', 'wf-1')
    expect(api.write).not.toHaveBeenCalled()
    expect(api.toast).toHaveBeenCalledWith('Could not generate share link.', 'error')
  })

  it('builds the tokenless extraction link unchanged', () => {
    expect(new URL(buildShareUrl('extraction', 'ss-1')).search).toBe('?extraction=ss-1')
  })
})
