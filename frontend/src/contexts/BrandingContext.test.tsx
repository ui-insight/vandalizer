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
    app_name: '',
    logo_data_url: '',
    icon_data_url: '',
    ...overrides,
  }
}

function Probe() {
  const b = useBranding()
  return <div data-testid="org">{b.orgName}</div>
}

/** Both names plus the attribution flag they feed. */
function NameProbe() {
  const b = useBranding()
  return (
    <>
      <div data-testid="org">{b.orgName}</div>
      <div data-testid="app">{b.appName}</div>
      <div data-testid="customized">{String(b.isCustomized)}</div>
    </>
  )
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

// ---------------------------------------------------------------------------
// The tool's name and the institution's name are separate fields (issue #819).
// app_name is what the assistant calls itself; org_name is a claim about an
// institution, and is what gets stamped into exports and creator credits.
// ---------------------------------------------------------------------------

describe('BrandingProvider — assistant name vs organization name', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(getThemeConfig).mockReset()
  })

  it('falls back to the org name when app_name is unset', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ org_name: 'Acme Research', app_name: '' }))

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Acme Research'))
    // The whole point of the fallback: an install that only ever set org_name
    // reads exactly as it did before app_name existed.
    expect(screen.getByTestId('app').textContent).toBe('Acme Research')
  })

  it('keeps the two apart when both are set', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(
      theme({ org_name: 'Acme Research', app_name: 'Scout' }),
    )

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('app').textContent).toBe('Scout'))
    expect(screen.getByTestId('org').textContent).toBe('Acme Research')
  })

  it('falls back to the built-in default when neither is set', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ org_name: '', app_name: '' }))

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(getThemeConfig).toHaveBeenCalled())
    expect(screen.getByTestId('org').textContent).toBe(DEFAULT_ORG_NAME)
    expect(screen.getByTestId('app').textContent).toBe(DEFAULT_ORG_NAME)
  })

  it('trims whitespace before deciding the app name is set', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(
      theme({ org_name: 'Acme Research', app_name: '   ' }),
    )

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('app').textContent).toBe('Acme Research'))
  })

  it('counts an app_name-only rebrand as customized', async () => {
    // Licence-compliance guard: isCustomized is what keeps "Powered by
    // Vandalizer" and the NSF GRANTED acknowledgement on screen (GPL v3).
    // Renaming only the assistant rebrands every conversational surface, so it
    // must trip the flag just as renaming the organization does.
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ org_name: '', app_name: 'Scout' }))

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('app').textContent).toBe('Scout'))
    expect(screen.getByTestId('org').textContent).toBe(DEFAULT_ORG_NAME)
    expect(screen.getByTestId('customized').textContent).toBe('true')
  })

  it('leaves an unbranded deployment uncustomized', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ org_name: '', app_name: '' }))

    render(
      <BrandingProvider>
        <NameProbe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(getThemeConfig).toHaveBeenCalled())
    expect(screen.getByTestId('customized').textContent).toBe('false')
  })
})
