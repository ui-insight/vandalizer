import { lazy, Suspense, useEffect } from 'react'
import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
  useNavigate,
  useRouterState,
} from '@tanstack/react-router'
import { useBranding } from './contexts/BrandingContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { useCertificationPanel } from './contexts/CertificationPanelContext'
import { Workspace } from './pages/Workspace'
import { TeamSettings } from './pages/TeamSettings'

const Landing = lazy(() => import('./pages/Landing'))
const Workflows = lazy(() => import('./pages/Workflows'))
const WorkflowEditor = lazy(() => import('./pages/WorkflowEditor'))
const Admin = lazy(() => import('./pages/Admin'))
const Account = lazy(() => import('./pages/Account'))
const Automation = lazy(() => import('./pages/Automation'))
const Verification = lazy(() => import('./pages/Verification'))
const SupportCenter = lazy(() => import('./pages/SupportCenter'))
const Docs = lazy(() => import('./pages/Docs'))
const Demo = lazy(() => import('./pages/Demo'))
const DemoFeedback = lazy(() => import('./pages/DemoFeedback'))
const DemoTrialEnd = lazy(() => import('./pages/DemoTrialEnd'))
const DemoResend = lazy(() => import('./pages/DemoResend'))
const InviteAccept = lazy(() => import('./pages/InviteAccept'))
const JoinLinkAccept = lazy(() => import('./pages/JoinLinkAccept'))
const JoinProjectAccept = lazy(() => import('./pages/JoinProjectAccept'))
const Organizations = lazy(() => import('./pages/Organizations'))
const Credentials = lazy(() => import('./pages/Credentials'))
const Reviews = lazy(() => import('./pages/Reviews'))
const ReviewDetail = lazy(() => import('./pages/ReviewDetail'))
const Login = lazy(() => import('./pages/Login'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const Present = lazy(() => import('./pages/present/Present'))

// Certification is now a dockable panel — this redirect opens it from old bookmarks
function CertificationRedirect() {
  const { openPanel } = useCertificationPanel()
  const navigate = useNavigate()
  useEffect(() => {
    openPanel()
    navigate({
      to: '/',
      search: {
        mode: undefined,
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
        project: undefined,
        workflow_share_token: undefined,
      },
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

// ---------------------------------------------------------------------------
// Route tree
// ---------------------------------------------------------------------------

// Per-route document titles (WCAG 2.4.2). Longest-prefix match; the workspace
// root falls back to the bare org name. Titles read "<Page> — <Org>".
const ROUTE_TITLES: Array<[string, string]> = [
  ['/workflows', 'Workflows'],
  ['/admin', 'Admin'],
  ['/account', 'Account'],
  ['/teams', 'Teams'],
  ['/organizations', 'Organizations'],
  ['/verification', 'Verification'],
  ['/support', 'Support'],
  ['/automation', 'Automations'],
  ['/docs', 'Docs'],
  ['/landing', 'Sign in'],
  ['/login', 'Sign in'],
  ['/register', 'Create account'],
  ['/reset-password', 'Reset password'],
  ['/invite', 'Accept invitation'],
  ['/demo', 'Demo'],
]

function RouteTitle() {
  const { orgName } = useBranding()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  useEffect(() => {
    const match = ROUTE_TITLES.find(([prefix]) => pathname === prefix || pathname.startsWith(prefix + '/'))
    document.title = match ? `${match[1]} — ${orgName}` : orgName
  }, [pathname, orgName])
  return null
}

const rootRoute = createRootRoute({
  component: () => (
    <Suspense fallback={<div className="p-6 text-gray-500 text-sm">Loading...</div>}>
      <RouteTitle />
      <Outlet />
    </Suspense>
  ),
})

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/landing',
  validateSearch: (search: Record<string, unknown>) => ({
    error: (search.error as string) || undefined,
    invite_token: (search.invite_token as string) || undefined,
    admin: (search.admin as string) || undefined,
    next: (search.next as string) || undefined,
  }),
  component: Landing,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: () => (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  ),
})

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/register',
  component: () => <Navigate to="/landing" search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined }} />,
})

const resetPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reset-password',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: () => (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  ),
})

const inviteRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/invite',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: InviteAccept,
})

const joinRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/join',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: JoinLinkAccept,
})

const joinProjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/join-project',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: JoinProjectAccept,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  validateSearch: (search: Record<string, unknown>) => ({
    // Workspace mode (chat is the default, omitted from URL when active)
    mode: (['chat', 'files', 'automations', 'knowledge', 'projects'].includes(search.mode as string)
      ? (search.mode as 'chat' | 'files' | 'automations' | 'knowledge' | 'projects')
      : undefined),
    // Active right panel tab (assistant is the default, omitted when active)
    tab: (['assistant', 'library'].includes(search.tab as string)
      ? (search.tab as 'assistant' | 'library')
      : undefined),
    // Open editor IDs — support legacy param names for backwards compat
    workflow: ((search.workflow as string) || (search.openWorkflow as string) || undefined),
    extraction: ((search.extraction as string) || (search.openExtraction as string) || undefined),
    automation: (search.automation as string) || undefined,
    kb: (search.kb as string) || undefined,
    // Project scope — present when arriving from "Chat with this project".
    project: (search.project as string) || undefined,
    // Share-link tokens — present when arriving from a "Copy share link" URL
    // and used to gate view-only access for users without team membership.
    workflow_share_token: (search.workflow_share_token as string) || undefined,
  }),
  component: () => (
    <ProtectedRoute>
      <Workspace />
    </ProtectedRoute>
  ),
})

const teamsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/teams',
  component: () => (
    <ProtectedRoute>
      <TeamSettings />
    </ProtectedRoute>
  ),
})


const workflowsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/workflows',
  component: () => (
    <ProtectedRoute>
      <Workflows />
    </ProtectedRoute>
  ),
})

const workflowEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/workflows/$id',
  component: () => (
    <ProtectedRoute>
      <WorkflowEditor />
    </ProtectedRoute>
  ),
})

// /chat and /library now live inside the workspace — redirect old URLs
const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: () => <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined }} />,
})

const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/library',
  component: () => <Navigate to="/" search={{ mode: undefined, tab: 'library', workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined }} />,
})

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin',
  component: () => (
    <ProtectedRoute>
      <Admin />
    </ProtectedRoute>
  ),
})

const accountRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/account',
  component: () => (
    <ProtectedRoute>
      <Account />
    </ProtectedRoute>
  ),
})

const automationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/automation',
  component: () => (
    <ProtectedRoute>
      <Automation />
    </ProtectedRoute>
  ),
})

const verificationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/verification',
  component: () => (
    <ProtectedRoute>
      <Verification />
    </ProtectedRoute>
  ),
})

const supportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/support',
  validateSearch: (search: Record<string, unknown>) => ({
    ticket: (search.ticket as string) || undefined,
  }),
  component: () => (
    <ProtectedRoute>
      <SupportCenter />
    </ProtectedRoute>
  ),
})

const docsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/docs',
  component: Docs,
})

// Present & Pitch — public communications surface, lives under /docs
const presentHubRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/docs/present',
  component: Present,
})

const presentTrackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/docs/present/$audience',
  validateSearch: (search: Record<string, unknown>) => ({
    mode: (search.mode === 'deck' ? 'deck' : undefined) as 'deck' | undefined,
    slide: (typeof search.slide === 'number'
      ? search.slide
      : typeof search.slide === 'string' && search.slide.trim() !== ''
        ? Number(search.slide) || undefined
        : undefined),
    pitch: (search.pitch === 'spoken' || search.pitch === 'written'
      ? (search.pitch as 'spoken' | 'written')
      : undefined),
  }),
  component: Present,
})

const demoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo',
  component: Demo,
})

const demoFeedbackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/feedback',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: DemoFeedback,
})

const demoTrialEndRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/trial-end',
  validateSearch: (search: Record<string, unknown>) => ({
    token: (search.token as string) || undefined,
  }),
  component: DemoTrialEnd,
})

const certificationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/certification',
  component: () => (
    <ProtectedRoute>
      <CertificationRedirect />
    </ProtectedRoute>
  ),
})

const organizationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/organizations',
  component: () => (
    <ProtectedRoute>
      <Organizations />
    </ProtectedRoute>
  ),
})

const credentialsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/credentials',
  component: () => (
    <ProtectedRoute>
      <Credentials />
    </ProtectedRoute>
  ),
})

// /audit is a tab in the Admin panel
const auditLogRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/audit',
  component: () => <Navigate to="/admin" search={{}} />,
})

const reviewsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reviews',
  component: () => (
    <ProtectedRoute>
      <Reviews />
    </ProtectedRoute>
  ),
})

const reviewDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reviews/$uuid',
  component: () => (
    <ProtectedRoute>
      <ReviewDetail />
    </ProtectedRoute>
  ),
})

// Redirect legacy bookmarks/email links from /approvals to /reviews
const approvalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/approvals',
  component: () => <Navigate to="/reviews" />,
})

// /office and /browser-automation are unlinked shadow routes — removed
const officeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/office',
  component: () => <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined }} />,
})

const browserAutomationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser-automation',
  component: () => <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined }} />,
})

const demoStatusRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/status/$uuid',
  component: Demo,
})

const demoResendRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/resend/$uuid',
  component: DemoResend,
})

const routeTree = rootRoute.addChildren([
  landingRoute,
  loginRoute,
  registerRoute,
  resetPasswordRoute,
  inviteRoute,
  joinRoute,
  joinProjectRoute,
  indexRoute,
  teamsRoute,
  workflowsRoute,
  workflowEditorRoute,
  chatRoute,
  libraryRoute,
  adminRoute,
  accountRoute,
  automationRoute,
  officeRoute,
  browserAutomationRoute,
  verificationRoute,
  supportRoute,
  docsRoute,
  presentHubRoute,
  presentTrackRoute,
  certificationRoute,
  demoRoute,
  demoFeedbackRoute,
  demoTrialEndRoute,
  demoStatusRoute,
  demoResendRoute,
  organizationsRoute,
  credentialsRoute,
  auditLogRoute,
  reviewsRoute,
  reviewDetailRoute,
  approvalsRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
