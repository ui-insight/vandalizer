import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CertProgressCard, CertModuleCard, CertCheckCard, CertCompletionCard } from './CertificationCards'

const h = vi.hoisted(() => ({
  sent: [] as string[],
  splitOpen: false,
  setSplit: [] as boolean[],
}))

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    sendChatMessage: (m: string) => { h.sent.push(m) },
    chatSplitOpen: h.splitOpen,
    setChatSplitOpen: (v: boolean) => { h.setSplit.push(v) },
  }),
}))

// Cards must render without a CertificationPanelProvider (null-safe hook).

const PROGRESS = {
  total_xp: 150,
  level: 'apprentice',
  certified: false,
  modules_completed: 2,
  modules_total: 11,
  next_module_id: 'process_mapping',
  modules: [
    { module_id: 'ai_literacy', title: 'AI Literacy', xp: 50, completed: true, stars: 3 },
    { module_id: 'foundations', title: 'Foundations', xp: 100, completed: true, stars: 2 },
    { module_id: 'process_mapping', title: 'Thinking in Workflows', xp: 100, completed: false, stars: 0 },
  ],
}

describe('CertProgressCard', () => {
  beforeEach(() => { h.sent = []; h.splitOpen = false; h.setSplit = [] })

  it('shows level, XP, and module completion', () => {
    render(<CertProgressCard content={PROGRESS} />)
    expect(screen.getByText(/2\/11 modules complete/)).toBeInTheDocument()
    expect(screen.getByText(/apprentice · 150 XP/i)).toBeInTheDocument()
    expect(screen.getByText('Foundations')).toBeInTheDocument()
  })

  it('continue button sends a chat message naming the next module', () => {
    render(<CertProgressCard content={PROGRESS} />)
    fireEvent.click(screen.getByRole('button', { name: /continue: thinking in workflows/i }))
    expect(h.sent[0]).toContain('Thinking in Workflows')
  })

  it('shows certified state instead of a continue button when done', () => {
    render(<CertProgressCard content={{ ...PROGRESS, certified: true, next_module_id: null }} />)
    expect(screen.getByText(/certified vandal workflow architect/i)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('CertModuleCard', () => {
  beforeEach(() => { h.sent = []; h.splitOpen = false; h.setSplit = [] })

  const MODULE = {
    module_id: 'foundations',
    title: 'Foundations',
    xp: 100,
    completed: false,
    stars: 0,
    overview: 'Build your first extraction.',
    instructions: ['Create an extraction template.', 'Run it on a sample document.'],
    expected_fields: ['pi_name', 'award_amount'],
    star_criteria: { '1': 'Pass all checks' },
    sample_documents: ['sample.pdf'],
    provisioned_docs: [],
    assessment_keys: [],
  }

  it('renders overview, instructions, and expected fields', () => {
    render(<CertModuleCard content={MODULE} />)
    expect(screen.getByText('Build your first extraction.')).toBeInTheDocument()
    expect(screen.getByText('Create an extraction template.')).toBeInTheDocument()
    expect(screen.getByText('pi_name')).toBeInTheDocument()
  })

  it('check-progress button sends a chat message', () => {
    render(<CertModuleCard content={MODULE} />)
    fireEvent.click(screen.getByRole('button', { name: /check my progress/i }))
    expect(h.sent[0]).toContain('Foundations')
  })

  it('offers split view when the module has sample documents', () => {
    render(<CertModuleCard content={MODULE} />)
    fireEvent.click(screen.getByRole('button', { name: /open files beside chat/i }))
    expect(h.setSplit).toEqual([true])
  })

  it('reflective modules get an assessment button, not a grading button', () => {
    render(<CertModuleCard content={{ ...MODULE, sample_documents: [], assessment_keys: ['experience', 'comfort', 'concern'] }} />)
    expect(screen.getByRole('button', { name: /reflection questions/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /check my progress/i })).not.toBeInTheDocument()
  })
})

describe('CertCheckCard', () => {
  beforeEach(() => { h.sent = [] })

  const CHECKS = {
    module_id: 'foundations',
    title: 'Foundations',
    passed: false,
    stars: 0,
    checks: [
      { name: 'Extraction template exists', passed: true, detail: '' },
      { name: 'Extraction executed', passed: false, detail: 'Run it at least once' },
    ],
  }

  it('renders each check with its detail and no complete button when failing', () => {
    render(<CertCheckCard content={CHECKS} />)
    expect(screen.getByText('Extraction template exists')).toBeInTheDocument()
    expect(screen.getByText(/run it at least once/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /complete the module/i })).not.toBeInTheDocument()
  })

  it('offers completion when all checks pass', () => {
    render(<CertCheckCard content={{ ...CHECKS, passed: true, stars: 2 }} />)
    fireEvent.click(screen.getByRole('button', { name: /complete the module/i }))
    expect(h.sent[0]).toContain('Foundations')
  })
})

describe('CertCompletionCard', () => {
  beforeEach(() => { h.sent = [] })

  it('shows XP earned and level', () => {
    render(<CertCompletionCard content={{
      module_id: 'foundations', title: 'Foundations',
      xp_earned: 100, total_xp: 250, stars: 2, level: 'builder', level_up: true, certified: false,
    }} />)
    expect(screen.getByText(/foundations complete/i)).toBeInTheDocument()
    expect(screen.getByText(/\+100 XP/)).toBeInTheDocument()
    expect(screen.getByText(/level up — builder/i)).toBeInTheDocument()
  })

  it('shows the certified banner on the final module', () => {
    render(<CertCompletionCard content={{
      module_id: 'governance', title: 'Governance',
      xp_earned: 300, total_xp: 1600, stars: 3, level: 'architect', level_up: true, certified: true,
    }} />)
    expect(screen.getByText(/certified vandal workflow architect/i)).toBeInTheDocument()
  })
})
