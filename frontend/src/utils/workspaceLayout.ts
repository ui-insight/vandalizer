export function validPanelSplit(value: number): number {
  return Number.isFinite(value) ? Math.min(80, Math.max(20, value)) : 60
}

/** Keep both panes useful without overwriting the preferred desktop split. */
export function panelSplitBounds(availableWidth: number) {
  if (!Number.isFinite(availableWidth) || availableWidth <= 0) return { min: 20, max: 80 }
  const min = Math.max(20, Math.min(50, 280 / availableWidth * 100))
  const max = Math.min(80, Math.max(50, 100 - 320 / availableWidth * 100))
  return { min, max }
}

export function fitPanelSplit(preferred: number, availableWidth: number) {
  const bounds = panelSplitBounds(availableWidth)
  return Math.max(bounds.min, Math.min(bounds.max, validPanelSplit(preferred)))
}

export const DEFAULT_RAIL_WIDTH = 320
const RAIL_KEY = 'workspace:railWidth'

/** Activity panel limits: wide enough for its filters, and never so wide the
 *  workspace beside it drops below a usable width. */
export function railWidthBounds(viewportWidth: number) {
  const min = 260
  const max = Number.isFinite(viewportWidth) ? Math.max(min, Math.min(560, viewportWidth - 88 - 600)) : 560
  return { min, max }
}

export function fitRailWidth(preferred: number, viewportWidth: number) {
  const { min, max } = railWidthBounds(viewportWidth)
  return Math.round(Math.max(min, Math.min(max, Number.isFinite(preferred) ? preferred : DEFAULT_RAIL_WIDTH)))
}

export function readRailWidth(): number {
  try {
    const saved = localStorage.getItem(RAIL_KEY)
    const width = saved && saved.trim() ? Number(saved) : NaN
    return Number.isFinite(width) ? width : DEFAULT_RAIL_WIDTH
  } catch { return DEFAULT_RAIL_WIDTH }
}

export function saveRailWidth(width: number) {
  try { localStorage.setItem(RAIL_KEY, String(Math.round(width))) } catch { /* The in-memory width still applies. */ }
}

type PanelChoice = 'source' | 'tools'
export type CompactPanelChoices = Partial<Record<string, PanelChoice>>
const KEY = 'workspace:compactPanels'
const MODES = ['files', 'projects', 'automations', 'knowledge', 'chat']
export function readCompactPanelChoices(): CompactPanelChoices {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || '{}')
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}
    return Object.fromEntries(Object.entries(saved).filter(([mode, choice]) => MODES.includes(mode) && (choice === 'source' || choice === 'tools'))) as CompactPanelChoices
  } catch { return {} }
}
export function saveCompactPanelChoices(choices: CompactPanelChoices) {
  try { sessionStorage.setItem(KEY, JSON.stringify(choices)) } catch { /* The in-memory choice still applies. */ }
}
