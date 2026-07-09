import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { OnboardingStatus } from '../../api/config'
import { FirstSessionHome, ReturningHome } from './HomeExperience'

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
  it('surfaces task-first onboarding and trust proof', () => {
    const onSendMessage = vi.fn()

    render(
      <FirstSessionHome
        orgName="Vandalizer"
        brandIcon={null}
        onRunDemo={vi.fn()}
        onAttachFiles={vi.fn()}
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    expect(screen.getByText('Turn complex documents into answers you can verify.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Upload a document/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run sample demo/i })).toBeInTheDocument()
    expect(screen.getByText('Sample answer from the demo')).toBeInTheDocument()
    expect(screen.getByText('Why the first answer feels trustworthy')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Extract deadlines/i }))
    expect(onSendMessage).toHaveBeenCalledWith(
      'Extract every deadline, deliverable, and owner from this document.',
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
        onFocusComposer={vi.fn()}
        onSendMessage={onSendMessage}
        status={baseStatus}
        suggestionPills={baseStatus.suggestion_pills}
      />,
    )

    expect(screen.getByText('A few items need attention')).toBeInTheDocument()
    expect(screen.getByText('Recent work and alerts')).toBeInTheDocument()
    expect(screen.getByText('Suggested next actions')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Resume recent work/i }))
    expect(onSendMessage).toHaveBeenCalledWith(
      'Show me the results from my "Budget review workflow" workflow run',
    )
  })
})
