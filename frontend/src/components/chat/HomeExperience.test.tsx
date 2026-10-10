import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import type { OnboardingStatus } from '../../api/config'
import type { CertificationProgress } from '../../types/certification'
import { CertificationPanelProvider, useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { FirstSessionHome, ReturningHome } from './HomeExperience'

// The certification CTA reads the shared cert progress. Mock the API the
// provider fetches from so tests control what "progress" the home sees.
const certApi = vi.hoisted(() => ({
  progress: null as CertificationProgress | null,
}))
vi.mock('../../api/certification', () => ({
  getProgress: () => Promise.resolve(certApi.progress),
  getCourse: () => Promise.resolve({ versioned: true, enrollment_id: certApi.progress?.enrollment_id, course_version: certApi.progress?.course_version, manifest_sha256: certApi.progress?.manifest_sha256, modules: [] }),
  validateModule: vi.fn(),
  completeModule: vi.fn(),
  provisionModule: vi.fn(),
  getExercise: vi.fn(),
  submitAssessment: vi.fn(),
}))

function withCert(children: ReactNode) {
  return <CertificationPanelProvider>{children}</CertificationPanelProvider>
}

function CoursePanelProbe() {
  const certification = useCertificationPanelOptional()
  return <output aria-label="Selected course panel">{certification?.isOpen ? `Open ${certification.progress?.enrollment_id}` : 'Closed'}</output>
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
      id: 'act-workflow-1',
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
    const onOpenActivity = vi.fn()

    render(
      <ReturningHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
        onOpenActivity={onOpenActivity}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Your workspace' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Recent work' })).toBeInTheDocument()
    expect(screen.getAllByText('Budget Review')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /Run Budget Review/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open results: Budget review workflow' }))
    expect(onOpenActivity).toHaveBeenCalledWith('act-workflow-1')
    expect(onSendMessage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask assistant about this warning' }))
    expect(onSendMessage).toHaveBeenCalledWith(expect.stringContaining('Do not run this tool on documents.'))
  })

  it('reopens the last conversation from the resume card instead of prompting the agent', () => {
    const onSendMessage = vi.fn()
    const onOpenActivity = vi.fn()
    const status: OnboardingStatus = {
      ...baseStatus,
      active_alerts: [],
      recent_activity: [{
        id: 'act-conv-1',
        type: 'conversation',
        title: 'Reviewing NSF Proposal Cover Sheet',
        relative_time: 'yesterday',
        status: 'completed',
      }],
    }

    render(
      <ReturningHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onChooseKnowledgeBase={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
        onOpenActivity={onOpenActivity}
        status={status}
        suggestionPills={status.suggestion_pills}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Continue chat/i }))
    expect(onOpenActivity).toHaveBeenCalledWith('act-conv-1')
    expect(onSendMessage).not.toHaveBeenCalled()
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
      onSendMessage={onSendMessage} onOpenActivity={vi.fn()} status={status} suggestionPills={[]} />)
    expect(screen.queryByText('Getting started')).not.toBeInTheDocument()
    if (mode === 'knowledge') {
      fireEvent.click(screen.getByRole('button', { name: 'Choose a knowledge base' }))
      expect(onChooseKnowledgeBase).toHaveBeenCalledOnce()
    } else {
      fireEvent.click(screen.getByRole('button', { name: 'Start a conversation' }))
      expect(onFocusComposer).toHaveBeenCalledOnce()
    }
  })

  it('puts real work before notices and selects an explicit source without running anything', () => {
    const onSelectDocument = vi.fn()
    const onSendMessage = vi.fn()
    render(<ReturningHome orgName="Vandalizer" brandIcon={null} onRunDemo={vi.fn()} onAttachFiles={vi.fn()}
      onChooseKnowledgeBase={vi.fn()} onFocusComposer={vi.fn()} onSendMessage={onSendMessage} onOpenActivity={vi.fn()}
      workQueue={<section aria-label="Project obligations">Project deadline</section>}
      status={{ ...baseStatus, recent_documents: [{ uuid: 'doc-1', title: 'Award notice.pdf' }] }}
      suggestionPills={baseStatus.suggestion_pills} onSelectDocument={onSelectDocument} />)
    const obligations = screen.getByRole('region', { name: 'Project obligations' })
    const notices = screen.getByRole('region', { name: 'Tool quality notices' })
    expect(obligations.compareDocumentPosition(notices) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Select document: Award notice.pdf' }))
    expect(onSelectDocument).toHaveBeenCalledWith({ uuid: 'doc-1', title: 'Award notice.pdf' })
    expect(onSendMessage).not.toHaveBeenCalled()
    expect(screen.queryByText(baseStatus.daily_guidance!)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /latest documents/i })).not.toBeInTheDocument()
  })

  it('separates an unfinished run from recent work without duplicating it', () => {
    render(<ReturningHome orgName="Vandalizer" brandIcon={null} onRunDemo={vi.fn()} onAttachFiles={vi.fn()}
      onChooseKnowledgeBase={vi.fn()} onFocusComposer={vi.fn()} onSendMessage={vi.fn()} onOpenActivity={vi.fn()}
      status={{ ...baseStatus, recent_activity: [{ ...baseStatus.recent_activity[0], status: 'running' }] }} suggestionPills={[]} />)
    expect(screen.getByRole('region', { name: 'Work in progress' })).toBeInTheDocument()
    expect(screen.getAllByText('Budget review workflow')).toHaveLength(1)
    expect(screen.queryByRole('region', { name: 'Recent work' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View progress: Budget review workflow' })).toBeInTheDocument()
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
        onOpenActivity={vi.fn()}
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
        onOpenActivity={vi.fn()}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    ))

    // Wait for the provider's progress fetch to settle, then assert absence.
    await screen.findByText('Recent work')
    await Promise.resolve()
    expect(screen.queryByRole('button', { name: /certification/i })).not.toBeInTheDocument()
  })
})


describe('selected certification course on home', () => {
  it.each(['first-new', 'first-active', 'first-completed', 'returning-new', 'returning-active', 'returning-completed'])('opens the selected course directly without a chat call when chat actions are disabled: %s', async variant => {
    const complete = variant.endsWith('completed')
    certApi.progress = { ...certProgress(variant.endsWith('new') ? [] : ['ai_literacy']), enrollment_id: 'selected-enrollment',
      course_version: 'original-course', manifest_sha256: 'a'.repeat(64), certified: complete }
    const onSendMessage = vi.fn()
    const props = { orgName: 'Vandalizer', brandIcon: null, disabled: true, onRunDemo: vi.fn(), onAttachFiles: vi.fn(),
      onChooseKnowledgeBase: vi.fn(), onFocusComposer: vi.fn(), onSendMessage }
    render(withCert(<>{variant.startsWith('first') ? <FirstSessionHome {...props} /> : <ReturningHome {...props} onOpenActivity={vi.fn()} status={baseStatus} suggestionPills={[]} />}<CoursePanelProbe /></>))
    const direct = await screen.findByRole('button', { name: complete ? 'Review completed course' : 'Open course without chat' })
    expect(direct).toBeEnabled()
    if (!complete) expect(screen.getByRole('button', { name: /certification/i })).toBeDisabled()
    fireEvent.click(direct)
    expect(screen.getByLabelText('Selected course panel')).toHaveTextContent('Open selected-enrollment')
    expect(onSendMessage).not.toHaveBeenCalled()
  })

  function home() {
    return render(withCert(<ReturningHome orgName="Vandalizer" brandIcon={null} onRunDemo={vi.fn()} onAttachFiles={vi.fn()}
      onChooseKnowledgeBase={vi.fn()} onFocusComposer={vi.fn()} onSendMessage={vi.fn()} onOpenActivity={vi.fn()}
      status={baseStatus} suggestionPills={[]} />))
  }

  it('counts only modules in the selected course and uses its own total', async () => {
    certApi.progress = { ...certProgress(['ai_literacy', 'retired_module']), enrollment_id: 'selected-course', course_version: 'v5-test', manifest_sha256: 'a'.repeat(64),
      module_ids: ['ai_literacy', 'new_module'], modules_total: 2 }
    home()
    expect(await screen.findByRole('button', { name: 'Continue certification (1/2)' })).toBeInTheDocument()
  })

  it.each(['lesson', 'assessment', 'scenario'])('offers continuation for saved %s work before the first module is completed', async kind => {
    certApi.progress = { ...certProgress([]), enrollment_id: 'selected-course', course_version: 'v5-test', manifest_sha256: 'a'.repeat(64),
      module_ids: ['ai_literacy'], modules_total: 1,
      ...(kind === 'lesson' ? { learning_position: { module_id: 'ai_literacy', lesson_id: 'lesson-one', revision: 1, content_sha256: 'c', saved_at: '2026-10-05' } }
        : kind === 'assessment' ? { pending_completions: [{ attempt_id: 'b'.repeat(32), module_id: 'ai_literacy', state: 'graded' as const, in_flight: false }] }
          : { modules: { ai_literacy: { completed: false, stars: 0, completed_at: null, attempts: 0, xp_earned: 0, scenario_attempt_id: 'd'.repeat(32) } } }) }
    home()
    expect(await screen.findByRole('button', { name: 'Continue certification (0/1)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start the certification course' })).not.toBeInTheDocument()
  })
})
