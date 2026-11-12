import { describe, expect, it } from 'vitest'
import { extractUrls } from './extractUrls'

describe('extractUrls', () => {
  it('pulls links out of an email', () => {
    const email = `Hi team,

Please add the new policy (https://www.uidaho.edu/policies/apm/45/13) and the
FAQ at https://osp.uidaho.edu/faq?tab=2&lang=en. Also www.nsf.gov/pappg, thanks!

-- Sent from my phone`
    expect(extractUrls(email)).toEqual([
      'https://www.uidaho.edu/policies/apm/45/13',
      'https://osp.uidaho.edu/faq?tab=2&lang=en',
      'https://www.nsf.gov/pappg',
    ])
  })

  it('keeps a link that has its own brackets', () => {
    expect(extractUrls('See https://en.wikipedia.org/wiki/Indirect_costs_(research).')).toEqual([
      'https://en.wikipedia.org/wiki/Indirect_costs_(research)',
    ])
  })

  it('reads href values from HTML and decodes &amp;', () => {
    const html = '<a href="https://a.gov/x?a=1&amp;b=2">x</a><a href=\'https://a.gov/y\'>y</a>'
    expect(extractUrls(html)).toEqual(['https://a.gov/x?a=1&b=2', 'https://a.gov/y'])
  })

  it('reads a CSV column', () => {
    expect(extractUrls('title,url\nPAPPG,https://nsf.gov/pappg\nGPS,"https://nih.gov/gps"\n')).toEqual([
      'https://nsf.gov/pappg', 'https://nih.gov/gps',
    ])
  })

  it('accepts a bare address alone on a line, as Add URLs always has', () => {
    expect(extractUrls('example.com/page1\n  grants.gov  \nnot a link.\nfoo')).toEqual([
      'https://example.com/page1', 'https://grants.gov',
    ])
  })

  it('drops repeats and keeps first-seen order', () => {
    expect(extractUrls('https://b.gov https://a.gov https://b.gov')).toEqual(['https://b.gov', 'https://a.gov'])
  })

  it('ignores e-mail addresses, other schemes and hostless links', () => {
    expect(extractUrls('mail jane@uidaho.edu or ftp://x.gov/f or http://localhost/ or https://a.gov')).toEqual([
      'https://a.gov',
    ])
  })
})
