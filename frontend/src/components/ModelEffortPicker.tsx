/**
 * ModelEffortPicker — displays the system-configured models as a radio-button
 * list with Intelligence / Speed / Privacy characteristic bars.
 *
 * Also exports:
 *   ModelCharacterBars   — standalone mini bars for use in admin model list rows
 */
import type { ModelInfo } from '../types/workflow'

// ---------------------------------------------------------------------------
// Scoring helpers
// ---------------------------------------------------------------------------

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
// ModelEffortPicker — list of system-configured models
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 8 }}>
      {models.map(model => {
        const selected = model.tag === selectedModel

        return (
          <button
            key={model.tag}
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
            {/* Row 1: radio dot + model name + tag */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{
                  width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                  border: selected ? '4.5px solid #3b82f6' : '2px solid #d1d5db',
                  backgroundColor: '#fff',
                  transition: 'border 0.12s',
                }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>{model.tag}</span>
                {model.external && (
                  <span style={{ fontSize: 10, color: '#9ca3af', fontWeight: 500 }}>external</span>
                )}
              </div>
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
