import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { uploadFile, getUploadPolicy } from '../api/files'
import { useChatUploads } from './useChatUploads'

vi.mock('../api/files', () => ({ uploadFile: vi.fn(), getUploadPolicy: vi.fn().mockResolvedValue({ extensions: ['txt', 'pdf'], max_size_bytes: 10 }) }))
const upload = vi.mocked(uploadFile)

describe('chat upload recovery', () => {
  beforeEach(() => { upload.mockReset() })

  it('keeps successful siblings attached and retries only the failed file', async () => {
    upload.mockImplementation(async data => {
      if (data.fileName === 'bad.txt') throw new Error('Transfer failed')
      return { complete: true, uuid: 'good' }
    })
    const attached = vi.fn()
    const { result } = renderHook(() => useChatUploads(attached))
    act(() => result.current.add([new File(['ok'], 'good.txt'), new File(['retry'], 'bad.txt')]))
    await waitFor(() => expect(result.current.uploading).toBe(false))
    expect(attached).toHaveBeenCalledWith('good', expect.objectContaining({ name: 'good.txt' }))
    expect(result.current.uploads).toHaveLength(1)
    expect(result.current.uploads[0].status).toBe('failed')
    upload.mockResolvedValueOnce({ complete: true, uuid: 'retried' })
    act(() => result.current.retry(result.current.uploads[0]))
    await waitFor(() => expect(result.current.uploads).toHaveLength(0))
    expect(upload).toHaveBeenCalledTimes(3)
    expect(attached).toHaveBeenCalledTimes(2)
    expect(attached).toHaveBeenLastCalledWith('retried', expect.objectContaining({ name: 'bad.txt' }))
  })

  it('aborts the active request and does not attach a late server response', async () => {
    let resolve!: (value: { complete: boolean; uuid: string }) => void
    upload.mockImplementation(() => new Promise(done => { resolve = done }))
    const attached = vi.fn()
    const { result } = renderHook(() => useChatUploads(attached))
    act(() => result.current.add([new File(['data'], 'cancel.txt')]))
    await waitFor(() => expect(upload).toHaveBeenCalledOnce())
    const signal = upload.mock.calls[0][1]!
    act(() => result.current.cancel(result.current.uploads[0].id))
    expect(signal.aborted).toBe(true)
    await act(async () => resolve({ complete: true, uuid: 'late' }))
    expect(attached).not.toHaveBeenCalled()
    expect(result.current.uploads[0].status).toBe('canceled')
  })

  it('treats a response without a document ID as a recoverable failure', async () => {
    upload.mockResolvedValue({ complete: true })
    const attached = vi.fn()
    const { result } = renderHook(() => useChatUploads(attached))
    act(() => result.current.add([new File(['data'], 'missing.txt')]))
    await waitFor(() => expect(result.current.uploads[0].status).toBe('failed'))
    expect(attached).not.toHaveBeenCalled()
  })
})


it('rejects unsupported and oversized files before transfer while keeping valid siblings', async () => {
  vi.mocked(getUploadPolicy).mockResolvedValue({ extensions: ['txt'], max_size_bytes: 10 })
  upload.mockReset().mockResolvedValue({ complete: true, uuid: 'valid' })
  const attached = vi.fn()
  const { result } = renderHook(() => useChatUploads(attached))
  act(() => result.current.add([new File(['x'], 'image.png'), new File(['01234567890'], 'large.txt'), new File(['small'], 'valid.txt')]))
  await waitFor(() => expect(result.current.uploading).toBe(false))
  expect(upload).toHaveBeenCalledOnce()
  expect(attached).toHaveBeenCalledWith('valid', expect.objectContaining({ name: 'valid.txt' }))
  expect(result.current.uploads.map(item => item.error).join(' ')).toContain('Unsupported file type')
  expect(result.current.uploads.map(item => item.error).join(' ')).toContain('per-file limit')
})
