import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const mockUploadFile = vi.fn()

vi.mock('../api/files', () => ({
  uploadFile: (...args: unknown[]) => mockUploadFile(...args),
}))

import { useUpload } from './useUpload'

const makeFile = (name: string) => new File(['content'], name)

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useUpload', () => {
  it('marks unsupported file types as failed without sending them to the server', async () => {
    const { result } = renderHook(() => useUpload(null, vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('photo.png')])
    })

    expect(mockUploadFile).not.toHaveBeenCalled()
    expect(result.current.uploads).toHaveLength(1)
    expect(result.current.uploads[0].error).toMatch(/Unsupported file type \(\.png\)/)
  })

  it('auto-clears successes after 3s but keeps failures visible', async () => {
    mockUploadFile
      .mockResolvedValueOnce({ uuid: 'u1' })
      .mockRejectedValueOnce(new Error('Server rejected file'))
    const { result } = renderHook(() => useUpload(null, vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('good.pdf'), makeFile('bad.docx')])
    })
    expect(result.current.uploads).toHaveLength(2)

    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.uploads).toHaveLength(1)
    expect(result.current.uploads[0].fileName).toBe('bad.docx')
    expect(result.current.uploads[0].error).toBe('Server rejected file')
  })

  it('auto-clears an all-success batch after 3s', async () => {
    mockUploadFile.mockResolvedValue({ uuid: 'u1' })
    const { result } = renderHook(() => useUpload(null, vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('good.pdf')])
    })
    expect(result.current.uploads).toHaveLength(1)

    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.uploads).toHaveLength(0)
  })

  it('dismissUpload removes a failed entry', async () => {
    mockUploadFile.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useUpload(null, vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('bad.pdf')])
    })
    expect(result.current.uploads).toHaveLength(1)

    act(() => {
      result.current.dismissUpload(result.current.uploads[0].id)
    })

    expect(result.current.uploads).toHaveLength(0)
  })

  it('keeps earlier failures visible when a new batch starts', async () => {
    mockUploadFile.mockRejectedValueOnce(new Error('boom')).mockResolvedValue({ uuid: 'u2' })
    const { result } = renderHook(() => useUpload(null, vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('bad.pdf')])
    })
    await act(async () => {
      await result.current.upload([makeFile('good.pdf')])
    })

    const names = result.current.uploads.map((u) => u.fileName)
    expect(names).toContain('bad.pdf')
    expect(names).toContain('good.pdf')
  })

  // Support ticket: re-uploading a revised file under the same name opened the
  // existing file, old content and all, as though the upload had worked.
  it('reports a same-name file with different content as not uploaded, and does not open the old one', async () => {
    mockUploadFile.mockResolvedValue({ complete: true, exists: true, uuid: 'old', changed: true })
    const { result } = renderHook(() => useUpload('folder-1', vi.fn()))

    await act(async () => {
      await result.current.upload([makeFile('budget.pdf')])
    })

    expect(result.current.uploads[0].error).toMatch(/A different file named \u201cbudget\.pdf\u201d is already in this folder/)
    expect(result.current.uploads[0].error).toMatch(/was not replaced/)
    expect(result.current.lastUploadedUuid).toBeNull()

    // It stays until dismissed, like any other failed upload.
    await act(async () => { vi.advanceTimersByTime(3000) })
    expect(result.current.uploads).toHaveLength(1)
  })

  it('still warns when the server cannot say whether the content differs', async () => {
    mockUploadFile.mockResolvedValue({ complete: true, exists: true, uuid: 'old', changed: null })
    const { result } = renderHook(() => useUpload('folder-1', vi.fn()))
    await act(async () => { await result.current.upload([makeFile('budget.pdf')]) })
    expect(result.current.uploads[0].error).toMatch(/was not updated/)
    expect(result.current.lastUploadedUuid).toBeNull()
  })

  it('opens the existing file and says nothing changed when the content is identical', async () => {
    mockUploadFile.mockResolvedValue({ complete: true, exists: true, uuid: 'old', changed: false })
    const { result } = renderHook(() => useUpload('folder-1', vi.fn()))
    await act(async () => { await result.current.upload([makeFile('budget.pdf')]) })
    expect(result.current.uploads[0].error).toBeUndefined()
    expect(result.current.uploads[0].note).toMatch(/same content/)
    expect(result.current.lastUploadedUuid).toBe('old')
  })
})
