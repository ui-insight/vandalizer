/**
 * ModelEffortPicker — converts raw model metadata into a Low / Med / High effort
 * radio-button picker with Intelligence / Speed / Privacy characteristic bars.
 *
 * Also exports:
 *   ModelCharacterBars   — standalone mini bars for use in admin model list rows
 *   effortLabelForModel  — returns "Low" | "Med" | "High" for a given model tag
 */
import type { ModelInfo } from '../types/workflow'

// ---------------------------------------------------------------------------
// Scoring helpers
// ---------------------------------------------------------------------------

/** Higher score = more capable / slower. */
function modelScore(m: ModelInfo): number {
  let s = m.tier === 'high' ? 3 : m.tier === 'standard' ? 2 : m.tier === 'basic' ? 1 : 1.5
  if (m.thinking) s += 1.5
  if (m.speed === 'fast') s -= 0.3
  else if (m.speed === 'slow') s += 0.3
  return s
}

function getIntelligenceScore(m: ModelInfo): number {
  let v = m.tier === 'high' ? 0.85 : m.tier === 'standard' ? 0.60 : m.tier === 'basic' ? 0.35 : 0.50
  if (m.thinking) v = Math.min(1, v + 0.15)
  return v
}

function getSpeedScore(m: ModelInfo): number {
  return m.speed === 'fast' ? 0.92 : m.speed === 'standard' ? 0.58 : m.speed === 'slow' ? 0.26 : 0.58
}

function getPrivacyScore(m: ModelInfo): number {
  return m.privacy === 'internal' ? 0.92 : m.privacy === 'external' ? 0.22 : 0.60
}

// ---------------------------------------------------------------------------
// Effort-level assignment
// ---------------------------------------------------------------------------

type EffortLevel = 'low' | 'med' | 'high'

const EFFORT_META: Record<EffortLevel, { label: string; description: string }> = {
  low:  { label: 'Low',    description: 'Fast & efficient' },
  med:  { label: 'Medium', description: 'Balanced performance' },
  high: { label: 'High',   description: 'Maximum capability' },
}

/** Assign the sorted models to Low / Med / High buckets. */
function assignEffortModels(models: ModelInfo[]): Record<EffortLevel, ModelInfo | null> {
  if (models.length === 0) return { low: null, med: null, high: null }
  const sorted = [...models].sort((a, b) => modelScore(a) - modelScore(b))
  const n = sorted.length
  return {
    low:  sorted[0],
    med:  sorted[Math.floor((n - 1) / 2)],
    high: sorted[n - 1],
  }
}

/** Returns "Low" | "Med" | "High" if the tag maps to a known effort level, else null. */
export function effortLabelForModel(models: ModelInfo[], tag: string): string | null {
  const assigned = assignEffortModels(models)
  for (const [level, model] of Object.entries(assigned) as [EffortLevel, ModelInfo | null][]) {
    if (model?.tag === tag) return EFFORT_META[level].label
  }
  return null
}

// ---------------------------------------------------------------------------
// Shared bar primitive
// ---------------------------------------------------------------------------

const BAR_COLORS = {
  intelligence: '#8b5cf6',
  speed:        '#f59e0b',
  privacy:      '#10b981',
}

function StatBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 10.5, color: '#9ca3af', width: 74, flexShrink: 0, fontWeight: 500 }}>{label}</span>
      <div style={{ flex: 1, height: 5, backgroundColor: '#efefef', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          width: `${Math.round(value * 100)}%`,
          height: '100%',
          backgroundColor: color,
          borderRadius: 3,
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ModelCharacterBars — small standalone bars for admin model rows
// ---------------------------------------------------------------------------

/** Pass a model from SystemConfigData.available_models (same shape as ModelInfo). */
export function ModelCharacterBars({ model }: { model: ModelInfo }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 170 }}>
      <StatBar label="Intelligence" value={getIntelligenceScore(model)} color={BAR_COLORS.intelligence} />
      <StatBar label="Speed"        value={getSpeedScore(model)}        color={BAR_COLORS.speed} />
      <StatBar label="Privacy"      value={getPrivacyScore(model)}      color={BAR_COLORS.privacy} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// ModelEffortPicker — 3-card radio picker for chat / user settings
// ---------------------------------------------------------------------------

interface PickerProps {
  models: ModelInfo[]
  selectedModel: string
  onChange: (tag: string) => void
}

export function ModelEffortPicker({ models, selectedModel, onChange }: PickerProps) {
  if (models.length === 0) {
    return (
      <div style={{ padding: '14px 16px', fontSize: 13, color: '#9ca3af', textAlign: 'center' }}>
        Loading models…
      </div>
    )
  }

  const assigned = assignEffortModels(models)
  const levels: EffortLevel[] = ['low', 'med', 'high']

  // Which level is currently selected?
  const selectedLevel = levels.find(l => assigned[l]?.tag === selectedModel) ?? null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 8 }}>
      {levels.map(level => {
        const model = assigned[level]
        if (!model) return null

        const selected = selectedLevel === level || (selectedLevel === null && model.tag === selectedModel)
        const meta = EFFORT_META[level]

        return (
          <button
            key={level}
            onClick={() => onChange(model.tag)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              padding: '12px 14px',
              backgroundColor: selected ? '#eff6ff' : '#fff',
              border: `${selected ? 2 : 1.5}px solid ${selected ? '#3b82f6' : '#e5e7eb'}`,
              borderRadius: 10,
              cursor: 'pointer',
              fontFamily: 'inherit',
              textAlign: 'left',
              width: '100%',
              transition: 'border-color 0.12s, background-color 0.12s',
            }}
          >
            {/* Row 1: radio dot + label + model tag */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{
                  width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                  border: selected ? '4.5px solid #3b82f6' : '2px solid #d1d5db',
                  backgroundColor: '#fff',
                  transition: 'border 0.12s',
                }} />
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>{meta.label}</span>
                  <span style={{ fontSize: 11, color: '#9ca3af' }}>{meta.description}</span>
                </div>
              </div>
              <span style={{
                fontSize: 10, color: '#b0b7c3', fontFamily: 'ui-monospace, monospace',
                maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {model.tag || model.name}
              </span>
            </div>

            {/* Row 2: characteristic bars */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 25 }}>
              <StatBar label="Intelligence" value={getIntelligenceScore(model)} color={BAR_COLORS.intelligence} />
              <StatBar label="Speed"        value={getSpeedScore(model)}        color={BAR_COLORS.speed} />
              <StatBar label="Privacy"      value={getPrivacyScore(model)}      color={BAR_COLORS.privacy} />
            </div>
          </button>
        )
      })}
    </div>
  )
}
