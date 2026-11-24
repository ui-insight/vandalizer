import { describe, expect, it } from 'vitest'
import { looksLikeAward } from './awardSuggestions'

describe('looksLikeAward', () => {
  it.each([
    'NIH_R01_Notice_of_Award.pdf', 'NOA-2025.pdf', 'FDP Subaward 123.pdf', 'Award Letter - Smith.docx',
    'NSF_grant_agreement.pdf', 'R21 NGA.pdf',
  ])('%s is an award', (name) => { expect(looksLikeAward(name)).toBe(true) })

  it.each(['Budget justification.xlsx', 'Biosketch.pdf', 'Awardee handbook draft.pdf', 'panorama.png', undefined])(
    '%s is not', (name) => { expect(looksLikeAward(name)).toBe(false) },
  )
})
