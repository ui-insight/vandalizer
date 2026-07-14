import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './markdown'

function buttons(html: string): Array<{ action: string; label: string }> {
  const out: Array<{ action: string; label: string }> = []
  const re = /<button data-action="([^"]+)"[^>]*>([^<]*)<\/button>/g
  let m: RegExpExecArray | null
  while ((m = re.exec(html))) out.push({ action: m[1], label: m[2] })
  return out
}

describe('renderMarkdown ACTION buttons', () => {
  it('renders the canonical form', () => {
    const html = renderMarkdown('Pick one:\n\n[ACTION:start-cert]Start the Certification Program[/ACTION]')
    expect(buttons(html)).toEqual([
      { action: 'start-cert', label: 'Start the Certification Program' },
    ])
    expect(html).not.toContain('[ACTION')
  })

  it('renders inside surrounding prose', () => {
    const html = renderMarkdown(
      'Here’s where you can dive in (no sample docs, which is expected).\n\n' +
      '[ACTION:start-cert]Start the Certification Program[/ACTION]\n\n' +
      'Would you like to open the lesson now?',
    )
    expect(buttons(html)).toHaveLength(1)
    expect(html).not.toContain('[ACTION')
  })

  it('tolerates backslash-escaped brackets', () => {
    const html = renderMarkdown('\\[ACTION:start-cert\\]Start the Certification Program\\[/ACTION\\]')
    expect(buttons(html)).toEqual([
      { action: 'start-cert', label: 'Start the Certification Program' },
    ])
  })

  it('tolerates backtick-wrapped tags', () => {
    const html = renderMarkdown('`[ACTION:upload-docs]Upload your documents[/ACTION]`')
    expect(buttons(html)).toEqual([
      { action: 'upload-docs', label: 'Upload your documents' },
    ])
    expect(html).not.toContain('&lt;button')
  })

  it('tolerates whitespace and lowercase action', () => {
    const html = renderMarkdown('[ action: start-cert ]Go[ /action ]'.replace('[ action', '[action'))
    expect(buttons(html)).toEqual([{ action: 'start-cert', label: 'Go' }])
  })

  it('handles the [Label][ACTION:type] mistake', () => {
    const html = renderMarkdown('[Upload your documents][ACTION:upload-docs]')
    expect(buttons(html)).toEqual([
      { action: 'upload-docs', label: 'Upload your documents' },
    ])
  })

  it('handles the [Label](ACTION:type) mistake', () => {
    const html = renderMarkdown('[Upload your documents](ACTION:upload-docs)')
    expect(buttons(html)).toEqual([
      { action: 'upload-docs', label: 'Upload your documents' },
    ])
  })

  it('converts a bare open tag using the known fallback label', () => {
    const html = renderMarkdown('Try this: [ACTION:start-cert]')
    expect(buttons(html)).toEqual([
      { action: 'start-cert', label: 'Start the Certification Program' },
    ])
  })

  it('humanizes unknown bare types so the click still sends a message', () => {
    const html = renderMarkdown('[ACTION:build-workflow]')
    expect(buttons(html)).toEqual([
      { action: 'build-workflow', label: 'Build workflow' },
    ])
  })

  it('drops a dangling close tag', () => {
    const html = renderMarkdown('done[/ACTION]')
    expect(html).not.toContain('ACTION')
    expect(html).toContain('done')
  })

  it('never leaks raw ACTION markup for any variant', () => {
    const variants = [
      '[ACTION:start-cert]Start[/ACTION]',
      '\\[ACTION:start-cert\\]Start\\[/ACTION\\]',
      '`[ACTION:start-cert]Start[/ACTION]`',
      '[action:start-cert]Start[/action]',
      '[Start][ACTION:start-cert]',
      '[Start](ACTION:start-cert)',
      '[ACTION:start-cert]',
    ]
    for (const v of variants) {
      const html = renderMarkdown(`before\n\n${v}\n\nafter`)
      expect(html, v).not.toMatch(/\[\\?\/?\s*ACTION/i)
      expect(buttons(html), v).toHaveLength(1)
    }
  })
})

describe('renderMarkdown sanitization', () => {
  it('keeps button + data-action through DOMPurify', () => {
    const html = renderMarkdown('[ACTION:start-cert]Go[/ACTION]')
    expect(html).toContain('data-action="start-cert"')
    expect(html).toContain('class="chat-action-btn"')
  })

  it('strips script tags', () => {
    const html = renderMarkdown('<script>alert(1)</script>hello')
    expect(html).not.toContain('<script>')
    expect(html).toContain('hello')
  })
})
