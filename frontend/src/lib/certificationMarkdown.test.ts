import { expect, it } from 'vitest'
import { renderCertificationMarkdown } from './certificationMarkdown'

it('renders authored exercise formatting while stripping executable markup', () => {
  const host = document.createElement('div')
  host.innerHTML = renderCertificationMarkdown('Ask: *"Check this source"*. Keep **PI Name** and `Total_Budget`.\n\n1. [Review the source](/files)\n2. Compare its value\n\n<img src="x" onerror="alert(1)"><script>alert(1)</script><button onclick="alert(1)">Run</button>[Unsafe](javascript:alert(1))')
  expect(host.querySelector('em')?.textContent).toBe('"Check this source"')
  expect(host.querySelector('strong')?.textContent).toBe('PI Name')
  expect(host.querySelector('code')?.textContent).toBe('Total_Budget')
  expect(host.querySelectorAll('ol li')).toHaveLength(2)
  expect(host.querySelector('a')?.getAttribute('href')).toBe('/files')
  expect(host.querySelector('script, button, [onerror], [onclick], [href^="javascript:"]')).toBeNull()
})
