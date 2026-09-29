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
