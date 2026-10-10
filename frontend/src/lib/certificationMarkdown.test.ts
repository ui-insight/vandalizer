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

it('keeps table headers and values in a named keyboard-scrollable region after sanitizing', () => {
  const host = document.createElement('div')
  host.innerHTML = renderCertificationMarkdown('| Source | Decision |\n| --- | --- |\n| Original notice | <img src="x" onerror="alert(1)">Review source |')
  const region = host.querySelector('[role="region"]')
  expect(region?.getAttribute('aria-label')).toBe('Course table 1')
  expect(region?.getAttribute('tabindex')).toBe('0')
  expect([...host.querySelectorAll('th')].map(cell => cell.textContent)).toEqual(['Source', 'Decision'])
  expect([...host.querySelectorAll('td')].map(cell => cell.textContent)).toEqual(['Original notice', 'Review source'])
  expect(host.querySelector('[onerror],script')).toBeNull()
})
