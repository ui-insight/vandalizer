import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrandingProvider, useBranding, DEFAULT_ORG_NAME } from './BrandingContext'
import type { ThemeConfig } from '../api/config'

vi.mock('../api/config', () => ({
  getThemeConfig: vi.fn(),
}))
import { getThemeConfig } from '../api/config'

const THEME_CACHE_KEY = 'vandalizer.theme'

function theme(overrides: Partial<ThemeConfig> = {}): ThemeConfig {
  return {
    highlight_color: '#123456',
    highlight_text_color: '#ffffff',
    highlight_complement: '#654321',
    ui_radius: '8px',
    org_name: 'Acme Research',
    logo_data_url: '',
    icon_data_url: '',
    ...overrides,
  }
}

function Probe() {
  const b = useBranding()
  return <div data-testid="org">{b.orgName}</div>
}

describe('BrandingProvider theme caching', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(getThemeConfig).mockReset()
  })

  it('paints the cached brand on first render, before the fetch resolves', async () => {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify(theme({ org_name: 'Cached Co' })))
    // Fetch never resolves during this assertion window — proves the first
    // paint comes from the cache, not the network.
    vi.mocked(getThemeConfig).mockReturnValue(new Promise(() => {}))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    expect(screen.getByTestId('org').textContent).toBe('Cached Co')
  })

  it('falls back to defaults on first render when nothing is cached', () => {
    vi.mocked(getThemeConfig).mockReturnValue(new Promise(() => {}))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    expect(screen.getByTestId('org').textContent).toBe(DEFAULT_ORG_NAME)
  })

  it('writes the fetched theme to the cache after a successful load', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ org_name: 'Fresh Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Fresh Co'))
    const cached = JSON.parse(localStorage.getItem(THEME_CACHE_KEY) || '{}')
    expect(cached.org_name).toBe('Fresh Co')
  })

  it('survives a corrupt cache entry without throwing', () => {
    localStorage.setItem(THEME_CACHE_KEY, '{not valid json')
    vi.mocked(getThemeConfig).mockReturnValue(new Promise(() => {}))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    // Bad cache → treated as no cache → defaults, no crash.
    expect(screen.getByTestId('org').textContent).toBe(DEFAULT_ORG_NAME)
  })
})
