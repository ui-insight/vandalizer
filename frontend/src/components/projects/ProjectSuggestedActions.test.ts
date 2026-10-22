import { describe, it, expect } from 'vitest'
import { buildProjectSuggestions } from './ProjectSuggestedActions'
import type { ProjectPin } from '../../types/project'

const wf: ProjectPin = { pin_type: 'workflow', target_id: 'wf-1', name: 'Compliance check' }
const ext: ProjectPin = { pin_type: 'extraction', target_id: 'ss-1', name: 'Budget fields' }
const auto: ProjectPin = { pin_type: 'automation', target_id: 'a-1', name: 'Auto sort' }
const kb: ProjectPin = { pin_type: 'knowledge_base', target_id: 'kb-1', name: 'NSF policy' }

describe('buildProjectSuggestions', () => {
  it('gives an owner a Run action per workflow/extraction pin, plus read-only helpers', () => {
    const out = buildProjectSuggestions([wf, ext], 'owner')
    const labels = out.map(s => s.label)
    expect(labels).toContain('Run Compliance check')
    expect(labels).toContain('Run Budget fields')
    expect(labels).toContain('Summarize this project')
    // The run message wording is the contract with the backend agent.
    const run = out.find(s => s.label === 'Run Compliance check')!
    expect(run.message).toBe('Run the "Compliance check" workflow on this project\'s documents.')
  })

  it('treats editors the same as owners (canAct)', () => {
    const out = buildProjectSuggestions([wf], 'editor')
    expect(out.some(s => s.label === 'Run Compliance check')).toBe(true)
  })

  it('hides Run actions from viewers, keeping only read-only helpers', () => {
    const out = buildProjectSuggestions([wf, ext], 'viewer')
    expect(out.some(s => s.label.startsWith('Run '))).toBe(false)
    expect(out.some(s => s.label === 'Summarize this project')).toBe(true)
  })

  it('excludes automation and knowledge_base pins from Run actions', () => {
    const out = buildProjectSuggestions([auto, kb], 'owner')
    expect(out.some(s => s.label.startsWith('Run '))).toBe(false)
  })

  it('shows just the read-only helpers when there are no pins', () => {
    const out = buildProjectSuggestions([], 'owner')
    const labels = out.map(s => s.label)
    expect(labels).toEqual([
      'Summarize this project',
      "What's missing from this project?",
      'What can I do next?',
    ])
  })

  it('caps the suggestion count at 6', () => {
    const manyPins: ProjectPin[] = Array.from({ length: 10 }, (_, i) => ({
      pin_type: 'workflow',
      target_id: `wf-${i}`,
      name: `Workflow ${i}`,
    }))
    const out = buildProjectSuggestions(manyPins, 'owner')
    expect(out.length).toBe(6)
  })
})
