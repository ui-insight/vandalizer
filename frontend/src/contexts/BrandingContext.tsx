import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { getThemeConfig, type ThemeConfig } from '../api/config'
import { getContrastTextColor, getComplementaryColor, getHoverColor } from '../utils/color'

export const DEFAULT_ORG_NAME = 'Vandalizer'
export const DEFAULT_LOGO_URL = '/images/Vandalizer_Wordmark_RGB.png'
export const DEFAULT_LOGO_DARK_URL = '/images/Vandalizer_Wordmark_Color_RGB+W.png'
export const DEFAULT_ICON_URL = '/images/joevandal.png'

export interface Branding {
  /** Display name for this deployment. Always non-empty (falls back to "Vandalizer"). */
  orgName: string
  /** Logo for light backgrounds. */
  logoUrl: string
  /** Logo for dark backgrounds (auth pages, footer). Same as logoUrl when admin uploads a custom one. */
  logoDarkUrl: string
  /**
   * Small square mascot/icon shown beside the wordmark (header, chat banners).
   * - Default (un-branded) deployment: the Joe Vandal mark.
   * - Custom icon uploaded: that icon.
   * - Branded (custom logo/name) but no custom icon: `null` — so Joe Vandal does
   *   NOT leak onto a white-labeled deployment. Render the icon only when set.
   */
  iconUrl: string | null
  /** True when the admin has overridden the default name. Used to surface "Powered by Vandalizer" attribution. */
  isCustomized: boolean
  /** Re-fetch from server (called by admin after saving theme). */
  refresh: () => Promise<void>
}

const BrandingContext = createContext<Branding | null>(null)

function applyTheme(theme: ThemeConfig) {
  const root = document.documentElement
  root.style.setProperty('--highlight-color', theme.highlight_color)
  root.style.setProperty('--ui-radius', theme.ui_radius)
  root.style.setProperty('--highlight-text-color', getContrastTextColor(theme.highlight_color))
  root.style.setProperty('--highlight-complement', getComplementaryColor(theme.highlight_color))
  root.style.setProperty('--highlight-hover', getHoverColor(theme.highlight_color))
}

function resolve(theme: ThemeConfig | null): Omit<Branding, 'refresh'> {
  const orgName = (theme?.org_name || '').trim() || DEFAULT_ORG_NAME
  const customLogo = (theme?.logo_data_url || '').trim()
  const customIcon = (theme?.icon_data_url || '').trim()
  const isCustomized = orgName !== DEFAULT_ORG_NAME || !!customLogo
  return {
    orgName,
    logoUrl: customLogo || DEFAULT_LOGO_URL,
    logoDarkUrl: customLogo || DEFAULT_LOGO_DARK_URL,
    iconUrl: customIcon || (isCustomized ? null : DEFAULT_ICON_URL),
    isCustomized,
  }
}

/** Point the browser-tab favicon at a custom icon (data URL) when one is set. */
function applyFavicon(iconUrl: string | null) {
  if (!iconUrl || !iconUrl.startsWith('data:')) return
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.href = iconUrl
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<Branding, 'refresh'>>(() => resolve(null))

  const load = useCallback(async () => {
    try {
      const theme = await getThemeConfig()
      applyTheme(theme)
      const resolved = resolve(theme)
      applyFavicon(resolved.iconUrl)
      setState(resolved)
    } catch {
      // Keep defaults if fetch fails (e.g., not logged in or backend down).
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Note: the document title is managed per-route by RouteTitle in router.tsx
  // (WCAG 2.4.2), which falls back to the bare org name on the workspace root.

  return (
    <BrandingContext.Provider value={{ ...state, refresh: load }}>
      {children}
    </BrandingContext.Provider>
  )
}

export function useBranding(): Branding {
  const ctx = useContext(BrandingContext)
  if (!ctx) {
    // Render-safe fallback so components used outside the provider (tests, storybook) still work.
    return {
      orgName: DEFAULT_ORG_NAME,
      logoUrl: DEFAULT_LOGO_URL,
      logoDarkUrl: DEFAULT_LOGO_DARK_URL,
      iconUrl: DEFAULT_ICON_URL,
      isCustomized: false,
      refresh: async () => {},
    }
  }
  return ctx
}
