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

const earnedCards = [
  { name: 'progress', Component: CertProgressCard, content: { ...PROGRESS, modules: [PROGRESS.modules[1]] } },
  { name: 'module', Component: CertModuleCard, content: { module_id: 'foundations', title: 'Foundations', completed: true, stars: 2, xp: 100 } },
  { name: 'check', Component: CertCheckCard, content: { module_id: 'foundations', title: 'Foundations', passed: true, stars: 2, checks: [{ name: 'Required evidence', passed: true, detail: 'Saved' }] } },
  { name: 'completion', Component: CertCompletionCard, content: { module_id: 'foundations', title: 'Foundations', stars: 2, xp_earned: 100, total_xp: 100, level: 'apprentice', certified: false } },
]

it.each(earnedCards)('uses the recorded reward policy in $name cards', ({ Component, content }) => {
  const { rerender } = render(<Component content={{ ...content, maximum_stars: 2, credit_basis: 'legacy_rubric' }} />)
  expect(screen.getByRole('img', { name: '2 of 2 stars' })).toBeInTheDocument()
  const outcomeContent = { ...content, stars: 1, modules: [{ ...PROGRESS.modules[1], stars: 1 }], maximum_stars: 1, credit_basis: 'required_outcomes' }
  rerender(<Component content={outcomeContent} />)
  expect(screen.queryByRole('img', { name: /stars/ })).not.toBeInTheDocument()
  expect(screen.getByText(/Foundations/)).toBeInTheDocument()
})

it('preserves historical star counts without inventing a missing versioned scale', () => {
  render(<CertCompletionCard content={{ ...earnedCards[3].content, enrollment_id: 'old-enrollment' }} />)
  expect(screen.getByRole('img', { name: '2 stars recorded' })).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: '2 of 3 stars' })).not.toBeInTheDocument()
})

describe('CertProgressCard', () => {
  beforeEach(() => { h.sent = []; h.splitOpen = false; h.setSplit = [] })

  it('renders the saved policy without replacing it with current panel rules or sending a message', () => {
    const policy = { policy_id: 'recorded-policy', state: 'design_draft', required_modules: 11, required_outcomes: 33, base_xp_total: 1850, rules: ['Saved policy: presentation choices do not change required evidence.'] }
    const { rerender } = render(<CertProgressCard content={{ ...PROGRESS, progression_policy: policy }} />)
    fireEvent.click(screen.getByText('How learning and credit work'))
    expect(screen.getByText(policy.rules[0])).toBeInTheDocument()
    expect(screen.getByText('Unpublished draft policy. This preview cannot award course credit.')).toBeInTheDocument()
    expect(h.sent).toEqual([])
    rerender(<CertProgressCard content={PROGRESS} />)
    expect(screen.queryByText('How learning and credit work')).not.toBeInTheDocument()
  })

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
    expect(screen.getByText('Course complete')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /continue:/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View earned certificates' })).toBeInTheDocument()
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
    const details = screen.getByText('Exercise instructions · 2 steps · 2 expected fields').closest('details')!
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByRole('button', { name: 'Check my progress' })).toBeVisible()
    expect(screen.getByText('Passing requirements')).toBeVisible()
    expect(screen.getByText('Pass all checks')).toBeVisible()
    fireEvent.click(screen.getByText('Exercise instructions · 2 steps · 2 expected fields'))
    expect(details).toHaveAttribute('open')
    expect(screen.getByText('Create an extraction template.')).toBeInTheDocument()
    expect(screen.getByText('pi_name')).toBeInTheDocument()
  })

  it('check-progress button sends a chat message', () => {
    render(<CertModuleCard content={MODULE} />)
    fireEvent.click(screen.getByRole('button', { name: /check my progress/i }))
    expect(h.sent[0]).toContain('Foundations')
  })

  it('keeps all required outcomes visible while detailed instructions are collapsed', () => {
    render(<CertModuleCard content={{ ...MODULE, star_criteria: {}, assessment_mode: 'selected_saved_outcomes',
      required_outcomes: [{ outcome_id: 'foundations.inspect', statement: 'Inspect the saved result against its source.' }] }} />)
    expect(screen.getByRole('heading', { name: 'Required outcomes' })).toBeVisible()
    expect(screen.getByText('Inspect the saved result against its source.')).toBeVisible()
    expect(screen.getByText(/All required outcomes must pass/)).toBeVisible()
    expect(screen.getByText(/Exercise instructions/).closest('details')).not.toHaveAttribute('open')
    expect(screen.queryByRole('img', { name: /stars/ })).not.toBeInTheDocument()
  })

  it('renders learner steps without inserting assistant coaching into the exercise', () => {
    render(<CertModuleCard content={{ ...MODULE, instructions: ['Inspect the assigned source.'],
      agent_guidance: ['Assistant: do not supply the learner’s approval decision.'] }} />)
    fireEvent.click(screen.getByText(/Exercise instructions/))
    expect(screen.getByText('Inspect the assigned source.')).toBeVisible()
    expect(screen.queryByText(/Assistant: do not supply/)).not.toBeInTheDocument()
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

  it('distinguishes an advisory suggestion from a required failure', () => {
    const checks = [
      { name: '15+ extraction fields', passed: true, role: 'required', detail: '' },
      { name: 'Missing expected fields', passed: false, role: 'advisory', detail: 'Consider adding the suggested fields.' },
    ]
    const { rerender } = render(<CertCheckCard content={{ ...CHECKS, passed: true, stars: 1, checks }} />)
    expect(screen.getByText('Module requirements met')).toBeVisible()
    expect(screen.getByText('— Advisory: Suggestion')).toBeVisible()
    expect(screen.getByText('Advisory suggestions do not block completion.')).toBeVisible()
    expect(screen.queryByText('All checks passed')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /complete the module/i })).toBeVisible()
    rerender(<CertCheckCard content={{ ...CHECKS, checks: [{ ...checks[0], passed: false }, checks[1]] }} />)
    expect(screen.getByText('— Required: Not met')).toBeVisible()
    expect(screen.queryByRole('button', { name: /complete the module/i })).not.toBeInTheDocument()
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
    expect(screen.getByText('Certification complete — the course requirements are complete.')).toBeInTheDocument()
  })
})
