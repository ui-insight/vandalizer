import { describe, it, expect } from 'vitest'
import { questionSetChanges, type QualityHistoryItem } from './QualityTimeline'

const run = (fp: string | null, source: string | null = null): QualityHistoryItem => ({
  source,
  question_set: fp ? { fingerprint: fp } : null,
})

describe('questionSetChanges', () => {
  it('flags a run whose question set differs from the previous run of its kind', () => {
    // Newest first, as history returns it.
    const items = [
      run('bbb'),                // full, differs from the previous full run (aaa)
      run('zzz', 'smoke_test'),  // subset, compared only with subsets
      run('aaa'),                // full, same as the older full run
      run('yyy', 'smoke_test'),
      run('aaa'),
      run(null),                 // legacy run with no snapshot: never compared
    ]
    expect(questionSetChanges(items)).toEqual([true, true, false, false, false, false])
  })
})
