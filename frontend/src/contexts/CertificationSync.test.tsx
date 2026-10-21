import { useEffect } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { CertificationProgress, CourseDefinition } from '../types/certification'
import type { ToolResultInfo } from '../types/chat'
import { CertificationPanelProvider, useCertificationPanel } from './CertificationPanelContext'
import { isCertificationWriteResult } from '../lib/certificationEvents'
import { FirstSessionHome } from '../components/chat/HomeExperience'
import { ActivityRail } from '../components/workspace/ActivityRail'
import persistedWrites from '../components/certification/__fixtures__/chat-write-contract.json'

// CHAT-05: every course write refreshes the one shared enrollment state that
// the panel, the home CTA and the rail badge all render, whether the write came
// from a chat tool result or a panel action.
const server = vi.hoisted(() => ({ progress: null as unknown as CertificationProgress, course: null as unknown as CourseDefinition }))
vi.mock('../api/certification', () => ({
  getProgress: vi.fn(() => Promise.resolve(server.progress)),
  getCourse: vi.fn(() => Promise.resolve(server.course)),
  validateModule: vi.fn(),
  completeModule: vi.fn(() => Promise.resolve({})),
  provisionModule: vi.fn(() => Promise.resolve({ module_id: 'foundations', provisioned_docs: [] })),
  submitAssessment: vi.fn(() => Promise.resolve({ stored: true })),
  getExercise: vi.fn(),
  savePosition: vi.fn(),
}))
vi.mock('../hooks/useActivities', () => ({ useActivities: () => ({ activities: [], loading: false, error: null, refresh: vi.fn(), staleThresholdMinutes: 30 }) }))
vi.mock('../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ count: 0 }) }))
vi.mock('../hooks/useOpenActivity', () => ({ pendingReviewUuid: () => null, useOpenActivity: () => vi.fn() }))
vi.mock('./WorkspaceContext', () => ({ useWorkspace: () => ({ railDocked: false, toggleRailDocked: vi.fn(), triggerNewChat: vi.fn(), focusChat: vi.fn(), activitySignal: 0, currentConversationUuid: null, openWorkflowId: null, openExtractionId: null }) }))
vi.mock('./ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../components/shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
import * as api from '../api/certification'

const MODULES = ['ai_literacy', 'foundations', 'workflows']
function course(version: string, enrollment: string, title: string, modules = MODULES): CourseDefinition {
  return { versioned: true, enrollment_id: enrollment, course_version: version, manifest_sha256: version.padEnd(64, '0').slice(0, 64), course_title: title,
    credential_scope: 'outcome_based', modules: modules.map(id => ({ id, title: id })), prerequisites: {} } as unknown as CourseDefinition
}
function progress(definition: CourseDefinition, modules: Record<string, object>, extra: Partial<CertificationProgress> = {}): CertificationProgress {
  return { id: `p-${definition.enrollment_id}`, user_id: 'u1', enrollment_id: definition.enrollment_id, course_version: definition.course_version,
    manifest_sha256: definition.manifest_sha256, module_ids: definition.modules.map(module => module.id), modules_total: definition.modules.length,
    modules, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, ...extra } as unknown as CertificationProgress
}

const handle: { current: ReturnType<typeof useCertificationPanel> | null } = { current: null }
function Panel() {
  const certification = useCertificationPanel()
  useEffect(() => { handle.current = certification })
  return <output aria-label="Panel course">{`${certification.progress?.course_version} ${certification.progress?.total_xp} XP`}</output>
}
// The same handler ChatPanel registers for live tool results.
function chatWrite(result: ToolResultInfo) {
  if (isCertificationWriteResult(result)) void handle.current!.refreshAfterWrite()
}
function renderSurfaces() {
  return render(<CertificationPanelProvider>
    <Panel />
    <FirstSessionHome orgName="Vandalizer" brandIcon={null} onRunDemo={vi.fn()} onAttachFiles={vi.fn()} onChooseKnowledgeBase={vi.fn()} onFocusComposer={vi.fn()} onSendMessage={vi.fn()} />
    <ActivityRail />
  </CertificationPanelProvider>)
}
const badge = () => screen.getByRole('button', { name: 'Open certification' })
async function expectSurfaces(panel: string, cta: string | null, badgeTitle: string) {
  await waitFor(() => expect(screen.getByLabelText('Panel course')).toHaveTextContent(panel))
  if (cta) expect(screen.getByRole('button', { name: cta })).toBeInTheDocument()
  else expect(screen.queryByRole('button', { name: /^(?:Start the certification course|Continue certification)/ })).toBeNull()
  expect(badge()).toHaveAttribute('title', badgeTitle)
}
const completed = persistedWrites.find(result => result.tool_name === 'complete_certification_module' && Number(result.content.xp_earned) > 0)!.content
const submitted = persistedWrites.find(result => result.tool_name === 'submit_certification_assessment')!.content
const provisioned = { module_id: 'foundations', provisioned_docs: [], document_names: [], folder: 'Certification Lab', message: 'No documents to provision' }

const v5 = course('5.0.0', 'e5', 'Agentic Workflow Practitioner')
beforeEach(() => {
  vi.clearAllMocks()
  server.course = v5
  server.progress = progress(v5, {})
})

it('updates panel, home CTA and rail badge from each chat write', async () => {
  renderSurfaces()
  await expectSurfaces('5.0.0 0 XP', 'Start the certification course', 'Get Certified')
  const reads = () => vi.mocked(api.getProgress).mock.calls.length
  const before = reads()

  server.progress = progress(v5, { foundations: { completed: false, provisioned_docs: ['d1'] } })
  act(() => chatWrite({ tool_name: 'provision_certification_lab', tool_call_id: 'lab', quality: null, content: provisioned }))
  await expectSurfaces('5.0.0 0 XP', 'Continue certification (0/3)', 'Get Certified')

  server.progress = progress(v5, { ai_literacy: { completed: false, self_assessment: { q1: 'answer' } } })
  act(() => chatWrite({ tool_name: 'submit_certification_assessment', tool_call_id: 'reflect', quality: null, content: submitted }))
  await expectSurfaces('5.0.0 0 XP', 'Continue certification (0/3)', 'Get Certified')

  server.progress = progress(v5, { ai_literacy: { completed: true, stars: 2 } }, { total_xp: 125, level: 'apprentice' })
  act(() => chatWrite({ tool_name: 'complete_certification_module', tool_call_id: 'done', quality: null, content: completed }))
  await expectSurfaces('5.0.0 125 XP', 'Continue certification (1/3)', 'Apprentice · 125 XP')

  // A star upgrade re-completes the same module: XP moves, the module count does not.
  server.progress = progress(v5, { ai_literacy: { completed: true, stars: 3 } }, { total_xp: 150, level: 'apprentice' })
  act(() => chatWrite({ tool_name: 'complete_certification_module', tool_call_id: 'stars', quality: null, content: { ...completed, stars: 3, total_xp: 150 } }))
  await expectSurfaces('5.0.0 150 XP', 'Continue certification (1/3)', 'Apprentice · 150 XP')
  expect(reads() - before).toBe(4)

  // Previews, errors and reads change nothing and read nothing.
  act(() => chatWrite({ tool_name: 'complete_certification_module', tool_call_id: 'preview', quality: null, content: { ...completed, needs_confirmation: true } }))
  act(() => chatWrite({ tool_name: 'get_certification_progress', tool_call_id: 'read', quality: null, content: { module_id: 'x', total_xp: 999 } }))
  await act(async () => { await Promise.resolve() })
  expect(reads() - before).toBe(4)
}, 20_000)

it('updates every surface after panel writes, graduation and a course switch', async () => {
  renderSurfaces()
  await expectSurfaces('5.0.0 0 XP', 'Start the certification course', 'Get Certified')

  server.progress = progress(v5, { foundations: { completed: false, provisioned_docs: ['d1'] } })
  await act(async () => { await handle.current!.provision('foundations') })
  await expectSurfaces('5.0.0 0 XP', 'Continue certification (0/3)', 'Get Certified')

  server.progress = progress(v5, Object.fromEntries(MODULES.map(id => [id, { completed: true, stars: 3 }])), { total_xp: 900, level: 'architect', certified: true })
  await act(async () => { await handle.current!.complete('workflows') })
  await expectSurfaces('5.0.0 900 XP', null, 'Agentic Workflow Practitioner')

  // Migration: an explicit course switch selects another enrollment; the
  // refresh that follows (ExplicitCourseSwitch.refreshAfterSave) re-reads it.
  const legacy = course('legacy-2026-10-02.1', 'e1', 'Vandal Workflow Architect', [...MODULES, 'governance'])
  server.course = legacy
  server.progress = progress(legacy, { ai_literacy: { completed: true, stars: 1 } }, { total_xp: 100, level: 'apprentice' })
  await act(async () => { await handle.current!.refresh() })
  await expectSurfaces('legacy-2026-10-02.1 100 XP', 'Continue certification (1/4)', 'Apprentice · 100 XP')
}, 20_000)
