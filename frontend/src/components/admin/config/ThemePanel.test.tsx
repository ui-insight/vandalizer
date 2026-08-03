import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ThemePanel } from './ThemePanel'

// ---------------------------------------------------------------------------
// The UI Theme & Branding panel in isolation (plan 013). It saves through the
// theme endpoint, applies the result to the document's CSS variables, and asks
// the branding context to refresh — in that order.
// ---------------------------------------------------------------------------

const mockGetThemeConfig = vi.fn()
const mockUpdateThemeConfig = vi.fn()

vi.mock('../../../api/config', () => ({
  getThemeConfig: (...a: unknown[]) => mockGetThemeConfig(...a),
  updateThemeConfig: (...a: unknown[]) => mockUpdateThemeConfig(...a),
}))

const mockBrandingRefresh = vi.fn()

vi.mock('../../../contexts/BrandingContext', () => ({
  useBranding: () => ({ refresh: mockBrandingRefresh }),
  DEFAULT_ORG_NAME: 'Vandalizer',
  DEFAULT_ICON_URL: '/images/joevandal.png',
}))

const THEME = {
  highlight_color: '#eab308',
  highlight_text_color: '#000000',
  highlight_complement: '#1e40af',
  ui_radius: '12px',
  org_name: 'Test University',
  logo_data_url: '',
  icon_data_url: '',
  icon_hide_in_nav: false,
}

/** The colour is bound to two inputs (a native picker and a hex field). */
function hexField() {
  return screen.getAllByDisplayValue(/^#/)[1]
}

beforeEach(() => {
  mockGetThemeConfig.mockReset().mockResolvedValue({ ...THEME })
  mockUpdateThemeConfig.mockReset().mockResolvedValue({ ...THEME })
  mockBrandingRefresh.mockReset().mockResolvedValue(undefined)
  document.documentElement.removeAttribute('style')
})

describe('ThemePanel — load', () => {
  it('renders the seeded values, then the theme endpoint takes over', async () => {
    render(<ThemePanel initialColor="#ff0000" initialRadius={4} />)

    // Seeded from the system config while the theme request is in flight.
    expect(hexField()).toHaveValue('#ff0000')
    expect(screen.getByText('Corner Radius: 4px')).toBeInTheDocument()

    // The theme endpoint is authoritative — it also carries the org name.
    await waitFor(() => expect(hexField()).toHaveValue('#eab308'))
    expect(screen.getByText('Corner Radius: 12px')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Test University')).toBeInTheDocument()
  })

  it('keeps the seeded values when the theme request fails', async () => {
    mockGetThemeConfig.mockRejectedValue(new Error('offline'))
    render(<ThemePanel initialColor="#ff0000" initialRadius={4} />)

    await waitFor(() => expect(mockGetThemeConfig).toHaveBeenCalled())
    expect(hexField()).toHaveValue('#ff0000')
    expect(screen.getByText('Corner Radius: 4px')).toBeInTheDocument()
  })
})

describe('ThemePanel — save', () => {
  it('sends the edited theme, applies it to the DOM and refreshes branding', async () => {
    mockUpdateThemeConfig.mockResolvedValue({ ...THEME, highlight_color: '#123456', ui_radius: '20px' })
    render(<ThemePanel initialColor="#eab308" initialRadius={12} />)
    await waitFor(() => expect(mockGetThemeConfig).toHaveBeenCalled())

    fireEvent.change(hexField(), { target: { value: '#123456' } })
    fireEvent.change(screen.getByDisplayValue('Test University'), { target: { value: '  Real University  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Theme' }))

    await waitFor(() => expect(mockUpdateThemeConfig).toHaveBeenCalledTimes(1))
    expect(mockUpdateThemeConfig).toHaveBeenCalledWith({
      highlight_color: '#123456',
      ui_radius: '12px',
      org_name: 'Real University',   // trimmed
      logo_data_url: '',
      icon_data_url: '',
      icon_hide_in_nav: false,
    })

    // The saved values, not the form's, are pushed onto the document.
    await waitFor(() => expect(document.documentElement.style.getPropertyValue('--highlight-color')).toBe('#123456'))
    expect(document.documentElement.style.getPropertyValue('--ui-radius')).toBe('20px')
    await waitFor(() => expect(mockBrandingRefresh).toHaveBeenCalled())
    expect(await screen.findByText('Theme saved!')).toBeInTheDocument()
  })

  it('sends the corner radius as a px string', async () => {
    render(<ThemePanel initialColor="#eab308" initialRadius={12} />)
    await waitFor(() => expect(mockGetThemeConfig).toHaveBeenCalled())

    fireEvent.change(screen.getByRole('slider'), { target: { value: '20' } })
    expect(screen.getByText('Corner Radius: 20px')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save Theme' }))
    await waitFor(() => expect(mockUpdateThemeConfig).toHaveBeenCalledWith(
      expect.objectContaining({ ui_radius: '20px' }),
    ))
  })

  it('surfaces a failed save instead of leaving the admin with no feedback', async () => {
    mockUpdateThemeConfig.mockRejectedValue(new Error('network unreachable'))
    render(<ThemePanel initialColor="#eab308" initialRadius={12} />)
    await waitFor(() => expect(mockGetThemeConfig).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Save Theme' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('network unreachable')
    // No false success, and no DOM/branding side effects from a failed save.
    expect(screen.queryByText('Theme saved!')).not.toBeInTheDocument()
    expect(mockBrandingRefresh).not.toHaveBeenCalled()
  })
})
