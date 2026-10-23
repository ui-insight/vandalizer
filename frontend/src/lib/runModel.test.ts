import { describe, it, expect } from 'vitest'
import { runModelLabel } from './runModel'

describe('runModelLabel', () => {
  it('names the model the steps ran on', () => {
    expect(runModelLabel({ model: 'VandalAI', models_used: ['moonshotai/kimi-k3'] })).toBe('Model: moonshotai/kimi-k3')
  })
  it('lists every model when steps ran on more than one', () => {
    expect(runModelLabel({ model: 'a', models_used: ['a', 'b'] })).toBe('Models: a, b')
  })
  it('falls back to the run model for older runs', () => {
    expect(runModelLabel({ model: 'VandalAI', models_used: [] })).toBe('Model: VandalAI')
  })
  it('is null when nothing was recorded', () => {
    expect(runModelLabel({})).toBeNull()
    expect(runModelLabel(null)).toBeNull()
  })
})
