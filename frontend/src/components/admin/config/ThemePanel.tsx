import { useEffect, useState } from 'react'
import { Palette } from 'lucide-react'
import { getThemeConfig, updateThemeConfig } from '../../../api/config'
import type { ThemeConfig } from '../../../api/config'
import { useBranding, DEFAULT_ORG_NAME, DEFAULT_ICON_URL } from '../../../contexts/BrandingContext'
import { fileToConstrainedDataUrl } from '../../../utils/imageResize'
import { sectionStyle, sectionHeaderStyle, sectionBodyStyle, labelStyle, inputStyle } from './styles'

function applyThemeToDOM(theme: ThemeConfig) {
  const root = document.documentElement
  root.style.setProperty('--highlight-color', theme.highlight_color)
  root.style.setProperty('--ui-radius', theme.ui_radius)
}

const MAX_LOGO_BYTES = 500_000 // matches backend cap on the encoded data URL

// ──────────────────────────────────────────
// UI theme & branding
// ──────────────────────────────────────────

export interface ThemePanelProps {
  /** Seed values from the system config, replaced by the theme endpoint's
   *  answer as soon as it lands. The theme endpoint is the authoritative
   *  source — it also carries the org name, logo and icon. */
  initialColor: string
  initialRadius: number
}

export function ThemePanel({ initialColor, initialRadius }: ThemePanelProps) {
  const branding = useBranding()
  const [themeColor, setThemeColor] = useState(initialColor)
  const [themeRadius, setThemeRadius] = useState(initialRadius)
  const [themeOrgName, setThemeOrgName] = useState('')
  const [themeLogo, setThemeLogo] = useState('')
  const [themeLogoError, setThemeLogoError] = useState<string | null>(null)
  const [themeIcon, setThemeIcon] = useState('')
  const [themeIconError, setThemeIconError] = useState<string | null>(null)
  const [themeIconHideInNav, setThemeIconHideInNav] = useState(false)
  const [themeSaving, setThemeSaving] = useState(false)
  const [themeSaved, setThemeSaved] = useState(false)
  const [themeError, setThemeError] = useState<string | null>(null)

  useEffect(() => {
    getThemeConfig().then(t => {
      setThemeColor(t.highlight_color)
      setThemeRadius(parseInt(t.ui_radius) || 12)
      setThemeOrgName(t.org_name || '')
      setThemeLogo(t.logo_data_url || '')
      setThemeIcon(t.icon_data_url || '')
      setThemeIconHideInNav(!!t.icon_hide_in_nav)
    }).catch(() => {})
  }, [])

  const handleSaveTheme = async () => {
    setThemeSaving(true)
    setThemeSaved(false)
    setThemeError(null)
    try {
      const updated = await updateThemeConfig({
        highlight_color: themeColor,
        ui_radius: `${themeRadius}px`,
        org_name: themeOrgName.trim(),
        logo_data_url: themeLogo,
        icon_data_url: themeIcon,
        icon_hide_in_nav: themeIconHideInNav,
      })
      applyThemeToDOM(updated)
      await branding.refresh()
      setThemeSaved(true)
      setTimeout(() => setThemeSaved(false), 3000)
    } catch (e) {
      setThemeError(e instanceof Error ? e.message : 'Failed to save theme')
    } finally {
      setThemeSaving(false)
    }
  }

  const handleLogoFile = async (file: File | null) => {
    setThemeLogoError(null)
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setThemeLogoError('Please choose an image file (PNG, SVG, JPG).')
      return
    }
    try {
      // Auto-downscale oversized raster images so large exports "just work".
      const dataUrl = await fileToConstrainedDataUrl(file, { maxBytes: MAX_LOGO_BYTES, maxDimension: 1024 })
      // Safety net for the rare oversized SVG, which is passed through unresized.
      if (dataUrl.length > MAX_LOGO_BYTES) {
        setThemeLogoError(`Image too large — keep encoded size under ${Math.round(MAX_LOGO_BYTES / 1024)} KB.`)
        return
      }
      setThemeLogo(dataUrl)
    } catch {
      setThemeLogoError('Could not process the selected image. Try a different file.')
    }
  }

  const handleIconFile = async (file: File | null) => {
    setThemeIconError(null)
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setThemeIconError('Please choose an image file (PNG, SVG, JPG).')
      return
    }
    try {
      // Icons/mascots are square-ish and small in the UI, so a tighter max
      // dimension keeps them well under the cap while staying crisp.
      const dataUrl = await fileToConstrainedDataUrl(file, { maxBytes: MAX_LOGO_BYTES, maxDimension: 512 })
      // Safety net for the rare oversized SVG, which is passed through unresized.
      if (dataUrl.length > MAX_LOGO_BYTES) {
        setThemeIconError(`Image too large — keep encoded size under ${Math.round(MAX_LOGO_BYTES / 1024)} KB.`)
        return
      }
      setThemeIcon(dataUrl)
    } catch {
      setThemeIconError('Could not process the selected image. Try a different file.')
    }
  }

  return (
    <div style={sectionStyle}>
      <div style={sectionHeaderStyle}>
        <Palette size={18} color="#6b7280" /> UI Theme &amp; Branding
      </div>
      <div style={sectionBodyStyle}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <label style={labelStyle}>Highlight Color</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <input type="color" value={themeColor} onChange={e => setThemeColor(e.target.value)} style={{ height: 40, width: 56, borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db', cursor: 'pointer' }} />
              <input type="text" value={themeColor} onChange={e => setThemeColor(e.target.value)} style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace' }} />
            </div>
          </div>
          <div>
            <label style={labelStyle}>Corner Radius: {themeRadius}px</label>
            <input type="range" min={0} max={24} value={themeRadius} onChange={e => setThemeRadius(Number(e.target.value))} style={{ width: '100%', marginTop: 8, accentColor: 'var(--highlight-color, #eab308)' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
              <span>0px (sharp)</span>
              <span>24px (round)</span>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 20 }}>
          <div>
            <label style={labelStyle}>Organization Name</label>
            <input
              type="text"
              value={themeOrgName}
              onChange={e => setThemeOrgName(e.target.value)}
              placeholder={DEFAULT_ORG_NAME}
              style={inputStyle}
            />
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
              Shown in the header, login page, browser tab, and chat greeting. Leave blank to keep "Vandalizer".
            </div>
          </div>
          <div>
            <label style={labelStyle}>Logo</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 180, height: 56, borderRadius: 'var(--ui-radius, 12px)',
                border: '1px solid #e5e7eb', background: '#f9fafb',
                display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
              }}>
                {themeLogo ? (
                  <img src={themeLogo} alt="Logo preview" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                ) : (
                  <img src="/images/Vandalizer_Wordmark_RGB.png" alt="Default Vandalizer logo" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', opacity: 0.7 }} />
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{
                  padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #d1d5db', background: '#fff',
                  fontSize: 12, fontWeight: 500, cursor: 'pointer', textAlign: 'center',
                }}>
                  {themeLogo ? 'Replace' : 'Upload'}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/svg+xml,image/webp"
                    onChange={e => handleLogoFile(e.target.files?.[0] || null)}
                    style={{ display: 'none' }}
                  />
                </label>
                {themeLogo && (
                  <button
                    type="button"
                    onClick={() => { setThemeLogo(''); setThemeLogoError(null) }}
                    style={{
                      padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)',
                      border: '1px solid #fee2e2', background: '#fff',
                      color: '#b91c1c', fontSize: 12, fontWeight: 500, cursor: 'pointer',
                    }}
                  >
                    Use default
                  </button>
                )}
              </div>
            </div>
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
              Wordmark-style image works best. PNG with transparency recommended. Large images are automatically resized to fit.
            </div>
            {themeLogoError && (
              <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 6 }}>{themeLogoError}</div>
            )}
          </div>
          <div>
            <label style={labelStyle}>Icon / Mascot</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 56, height: 56, borderRadius: 'var(--ui-radius, 12px)',
                border: '1px solid #e5e7eb', background: '#f9fafb',
                display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
              }}>
                {themeIcon ? (
                  <img src={themeIcon} alt="Icon preview" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                ) : (
                  <img src={DEFAULT_ICON_URL} alt="Default Joe Vandal icon" style={{ maxWidth: '70%', maxHeight: '90%', objectFit: 'contain', opacity: 0.7 }} />
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{
                  padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #d1d5db', background: '#fff',
                  fontSize: 12, fontWeight: 500, cursor: 'pointer', textAlign: 'center',
                }}>
                  {themeIcon ? 'Replace' : 'Upload'}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/svg+xml,image/webp"
                    onChange={e => handleIconFile(e.target.files?.[0] || null)}
                    style={{ display: 'none' }}
                  />
                </label>
                {themeIcon && (
                  <button
                    type="button"
                    onClick={() => { setThemeIcon(''); setThemeIconError(null) }}
                    style={{
                      padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)',
                      border: '1px solid #fee2e2', background: '#fff',
                      color: '#b91c1c', fontSize: 12, fontWeight: 500, cursor: 'pointer',
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
              Small square mark shown beside the logo (header & chat) and as the browser-tab favicon. A square, transparent PNG works best. The default Joe Vandal mark shows only on un-branded deployments — once you set an organization name or logo, leave this blank to hide it, or upload your own.
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#374151', marginTop: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={themeIconHideInNav}
                onChange={e => setThemeIconHideInNav(e.target.checked)}
              />
              Hide icon from the navigation header (still used as favicon and chat avatar)
            </label>
            {themeIconError && (
              <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 6 }}>{themeIconError}</div>
            )}
          </div>
        </div>

        <div style={{
          marginTop: 16, padding: 12, background: '#f9fafb',
          borderRadius: 'var(--ui-radius, 12px)', border: '1px dashed #e5e7eb',
          fontSize: 12, color: '#6b7280', lineHeight: 1.5,
        }}>
          Vandalizer is open source under the GPL v3 license and developed at the University of Idaho with support from the NSF GRANTED program (Award #2427549). Even with your custom branding applied, the footer will continue to credit the Vandalizer project and acknowledge NSF funding.
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
          <div style={{ backgroundColor: themeColor, borderRadius: `${themeRadius}px`, padding: '8px 20px', color: 'var(--highlight-text-color, #000)', fontWeight: 600, fontSize: 13 }}>
            Sample Button
          </div>
          <div style={{ border: `2px solid ${themeColor}`, borderRadius: `${themeRadius}px`, padding: '8px 20px', color: themeColor, fontWeight: 600, fontSize: 13 }}>
            Outline Button
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
          <button
            onClick={handleSaveTheme}
            disabled={themeSaving}
            style={{
              padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
              background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              opacity: themeSaving ? 0.6 : 1,
            }}
          >
            {themeSaving ? 'Saving...' : 'Save Theme'}
          </button>
          {themeSaved && <span role="status" aria-live="polite" style={{ fontSize: 13, color: '#16a34a' }}>Theme saved!</span>}
        </div>
        {themeError && (
          <div role="alert" style={{ marginTop: 12, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
            {themeError}
          </div>
        )}
      </div>
    </div>
  )
}
