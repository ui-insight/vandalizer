import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import type { OnboardingStatus } from '../../api/config'
import type { CertificationProgress } from '../../types/certification'
import { CertificationPanelProvider } from '../../contexts/CertificationPanelContext'
import { FirstSessionHome, ReturningHome } from './HomeExperience'

// The certification CTA reads the shared cert progress. Mock the API the
// provider fetches from so tests control what "progress" the home sees.
const certApi = vi.hoisted(() => ({
  progress: null as CertificationProgress | null,
}))
vi.mock('../../api/certification', () => ({
  getProgress: () => Promise.resolve(certApi.progress),
  validateModule: vi.fn(),
  completeModule: vi.fn(),
  provisionModule: vi.fn(),
  getExercise: vi.fn(),
  submitAssessment: vi.fn(),
}))

function withCert(children: ReactNode) {
  return <CertificationPanelProvider>{children}</CertificationPanelProvider>
}

function certProgress(completedModules: string[]): CertificationProgress {
  return {
    id: 'p1',
    user_id: 'u1',
    modules: Object.fromEntries(completedModules.map((m) => [m, {
      completed: true, stars: 2, completed_at: null, attempts: 1, xp_earned: 100,
    }])),
    total_xp: completedModules.length * 100,
    level: 'apprentice',
    certified: false,
    certified_at: null,
    last_activity_date: null,
  }
}

const baseStatus: OnboardingStatus = {
  has_documents: true,
  has_workflows: true,
  has_run_workflow: true,
  has_extraction_sets: true,
  has_library_items: true,
  has_pinned_item: false,
  has_favorited_item: false,
  has_team_members: false,
  has_automations: false,
  has_enabled_automation: false,
  has_knowledge_base: true,
  has_ready_knowledge_base: true,
  has_chatted_with_docs: true,
  has_conversations: true,
  first_session_completed: true,
  is_certified: false,
  suggestion_pills: [
    'Run Budget Review on my latest documents',
    'Check quality score for Budget Review',
    'Compare the latest two policy revisions',
  ],
  has_only_onboarding_docs: false,
  top_extraction_set_name: 'Budget Review',
  top_workflow_name: 'Budget Review Workflow',
  recent_activity: [
    {
      type: 'workflow_run',
      title: 'Budget review workflow',
      relative_time: '2 hours ago',
      status: 'completed',
    },
  ],
  active_alerts: [
    {
      message: 'Budget Review quality score dropped below target',
      severity: 'warning',
      item_name: 'Budget Review',
    },
  ],
  maturity_stage: 'practitioner',
  unprocessed_doc_count: 2,
  daily_guidance: 'Resume your budget review workflow and check the related quality alert.',
  since_last_visit: 'Since you were last here (2 days ago): 1 run completed successfully',
}

describe('FirstSessionHome', () => {
  it('offers conversation, knowledge, documents, and agent work as starting points', () => {
    const onSendMessage = vi.fn()
    const onFocusComposer = vi.fn()
    const onChooseKnowledgeBase = vi.fn()

    render(
      <FirstSessionHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={onChooseKnowledgeBase}
        onFocusComposer={onFocusComposer}
        onSendMessage={onSendMessage}
      />,
    )

    expect(screen.getByText('What would you like to get done?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload a document' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a conversation' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose a knowledge base' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start a conversation' }))
    expect(onFocusComposer).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Choose a knowledge base' }))
    expect(onChooseKnowledgeBase).toHaveBeenCalledOnce()
    expect(onSendMessage).not.toHaveBeenCalled()
    expect(screen.queryByRole('list', { name: 'Your first task' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run sample demo' })).not.toBeVisible()
    fireEvent.click(screen.getByText('Try a sample document demo'))
    expect(screen.getByRole('button', { name: 'Run sample demo' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Build a workflow' }))
    expect(onSendMessage).toHaveBeenCalledWith('Help me turn a recurring task into a workflow.')
  })

  it('offers to start the certification course in chat', () => {
    const onSendMessage = vi.fn()
    certApi.progress = null

    render(withCert(
      <FirstSessionHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    ))

    fireEvent.click(screen.getByRole('button', { name: /start the certification course/i }))
    expect(onSendMessage).toHaveBeenCalledWith(
      'Start the Vandalizer certification course — show me where to begin.',
    )
  })
})

describe('ReturningHome', () => {
  it('helps returning users resume work and review issues', () => {
    const onSendMessage = vi.fn()

    render(
      <ReturningHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    )

    expect(screen.getByText('Review what changed since your last visit')).toBeInTheDocument()
    expect(screen.getByText('Continue where you left off')).toBeInTheDocument()
    expect(screen.getByText('Suggested questions')).toBeInTheDocument()
    expect(screen.getByText('Ready in this workspace')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Review alert/i }))
    expect(onSendMessage).toHaveBeenNthCalledWith(1, 'Check quality of Budget Review')

    fireEvent.click(screen.getByRole('button', { name: /Budget review workflow/i }))
    expect(onSendMessage).toHaveBeenNthCalledWith(
      2,
      'Show me the results from my "Budget review workflow" workflow run',
    )
  })

  it.each(['empty', 'knowledge', 'workflows', 'sample', 'unavailable'] as const)('offers useful work without requiring uploads: %s', (mode) => {
    const onFocusComposer = vi.fn()
    const onChooseKnowledgeBase = vi.fn()
    const onSendMessage = vi.fn()
    const status = mode === 'unavailable' ? null : {
      ...baseStatus, has_documents: mode === 'sample', has_only_onboarding_docs: mode === 'sample',
      has_workflows: mode === 'workflows', has_ready_knowledge_base: mode === 'knowledge',
      has_knowledge_base: mode === 'knowledge', recent_activity: [], active_alerts: [],
      unprocessed_doc_count: 0, suggestion_pills: [], daily_guidance: null,
    }
    render(<ReturningHome orgName="Vandalizer" brandIcon={null} onRunDemo={vi.fn()}
      onAttachFiles={vi.fn()} onFocusComposer={onFocusComposer} onChooseKnowledgeBase={onChooseKnowledgeBase}
      onSendMessage={onSendMessage} status={status} suggestionPills={[]} />)
    expect(screen.queryByText('Getting started')).not.toBeInTheDocument()
    if (mode === 'knowledge') {
      fireEvent.click(screen.getByRole('button', { name: 'Choose a knowledge base' }))
      expect(onChooseKnowledgeBase).toHaveBeenCalledOnce()
    } else if (mode === 'workflows') {
      fireEvent.click(screen.getByRole('button', { name: 'Find a workflow' }))
      expect(onSendMessage).toHaveBeenCalledWith('List my available workflows and help me choose one for my next task.')
    } else {
      fireEvent.click(screen.getByRole('button', { name: 'Start a conversation' }))
      expect(onFocusComposer).toHaveBeenCalledOnce()
    }
  })

  it('shows a continue-certification CTA with the completed count', async () => {
    const onSendMessage = vi.fn()
    certApi.progress = certProgress(['ai_literacy', 'foundations'])

    render(withCert(
      <ReturningHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    ))

    const btn = await screen.findByRole('button', { name: /continue certification \(2\/11\)/i })
    fireEvent.click(btn)
    expect(onSendMessage).toHaveBeenCalledWith(
      'Continue my certification — show my progress and the next module.',
    )
  })

  it('hides the certification CTA once certified', async () => {
    certApi.progress = { ...certProgress(['ai_literacy']), certified: true }

    render(withCert(
      <ReturningHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={vi.fn()}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    ))

    // Wait for the provider's progress fetch to settle, then assert absence.
    await screen.findByText('Suggested questions')
    await Promise.resolve()
    expect(screen.queryByRole('button', { name: /certification/i })).not.toBeInTheDocument()
  })
})
