import { describe, it, expect } from 'vitest'
import { partitionNewFiles } from './attachmentDedup'

describe('partitionNewFiles', () => {
  it('uploads everything when nothing is attached', () => {
    const { toUpload, dupes } = partitionNewFiles(['a.pdf', 'b.pdf'], [])
    expect(toUpload).toEqual(['a.pdf', 'b.pdf'])
    expect(dupes).toEqual([])
  })

  it('skips a file already attached (the double-drop case)', () => {
    const { toUpload, dupes } = partitionNewFiles(['19E777.pdf'], ['19E777.pdf'])
    expect(toUpload).toEqual([])
    expect(dupes).toEqual(['19E777.pdf'])
  })

  it('dedups repeats within the same batch', () => {
    const { toUpload, dupes } = partitionNewFiles(['x.pdf', 'x.pdf', 'y.pdf'], [])
    expect(toUpload).toEqual(['x.pdf', 'y.pdf'])
    expect(dupes).toEqual(['x.pdf'])
  })

  it('keeps new files while skipping the already-attached ones', () => {
    const { toUpload, dupes } = partitionNewFiles(['a.pdf', 'b.pdf'], ['a.pdf'])
    expect(toUpload).toEqual(['b.pdf'])
    expect(dupes).toEqual(['a.pdf'])
  })
})
