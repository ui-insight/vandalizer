import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrandingProvider, useBranding, DEFAULT_ORG_NAME } from './BrandingContext'
import { contrastRatio, getAccessibleOnDark, getPanelDark } from '../utils/color'
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

describe('BrandingProvider derived CSS variables', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(getThemeConfig).mockReset()
    document.documentElement.removeAttribute('style')
  })

  it('sets --highlight-on-dark from the resolved theme', async () => {
    // #163A64 is ~1.6:1 on the #0a0a0a auth/footer surface — unusable raw.
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ highlight_color: '#163A64', org_name: 'Navy Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Navy Co'))
    const value = document.documentElement.style.getPropertyValue('--highlight-on-dark')
    expect(value).toBe(getAccessibleOnDark('#163A64'))
    expect(contrastRatio(value, '#0a0a0a')).toBeGreaterThanOrEqual(4.5)
  })

  it('sets --highlight-on-dark from the cached theme on first render', () => {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify(theme({ highlight_color: '#163A64' })))
    vi.mocked(getThemeConfig).mockReturnValue(new Promise(() => {}))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    expect(document.documentElement.style.getPropertyValue('--highlight-on-dark')).toBe(
      getAccessibleOnDark('#163A64'),
    )
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

  it('sets --panel-dark from the resolved theme', async () => {
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ highlight_color: '#163A64', org_name: 'Navy Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Navy Co'))
    const value = document.documentElement.style.getPropertyValue('--panel-dark')
    expect(value).toBe(getPanelDark('#163A64'))
    // Lightness is pinned, so the chrome stays as legible as the #191919 it replaces.
    expect(contrastRatio(value, '#ffffff')).toBeGreaterThan(15)
  })

  it('sets --panel-dark from the cached theme on first render', () => {
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify(theme({ highlight_color: '#163A64' })))
    vi.mocked(getThemeConfig).mockReturnValue(new Promise(() => {}))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    expect(document.documentElement.style.getPropertyValue('--panel-dark')).toBe(
      getPanelDark('#163A64'),
    )
  })

  it('leaves --panel-dark unset for the untouched default brand color', async () => {
    // #eab308 is the theme default: the admin never picked a brand, so the
    // chrome must stay the neutral #191919 that the :root fallback supplies.
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ highlight_color: '#eab308', org_name: 'Plain Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Plain Co'))
    expect(document.documentElement.style.getPropertyValue('--panel-dark')).toBe('')
  })

  it('leaves --panel-dark unset when the stored brand colour is not a colour', async () => {
    // A malformed value must fall back to the neutral chrome, not paint an
    // invalid var() that makes the whole shell transparent.
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ highlight_color: '#12', org_name: 'Broken Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Broken Co'))
    expect(document.documentElement.style.getPropertyValue('--panel-dark')).toBe('')
  })

  it('clears a cached brand tint when the admin resets to the default color', async () => {
    // First render paints navy from cache; the server then reports the default.
    // Without removeProperty the stale navy would outlive the reset.
    localStorage.setItem(THEME_CACHE_KEY, JSON.stringify(theme({ highlight_color: '#163A64' })))
    vi.mocked(getThemeConfig).mockResolvedValue(theme({ highlight_color: '#eab308', org_name: 'Reset Co' }))

    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>,
    )

    expect(document.documentElement.style.getPropertyValue('--panel-dark')).toBe(getPanelDark('#163A64'))
    await waitFor(() => expect(screen.getByTestId('org').textContent).toBe('Reset Co'))
    expect(document.documentElement.style.getPropertyValue('--panel-dark')).toBe('')
  })
})
