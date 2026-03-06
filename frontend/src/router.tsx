import { lazy, Suspense } from 'react'
import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
} from '@tanstack/react-router'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { Workspace } from './pages/Workspace'
import { TeamSettings } from './pages/TeamSettings'

const Landing = lazy(() => import('./pages/Landing'))
const Workflows = lazy(() => import('./pages/Workflows'))
const WorkflowEditor = lazy(() => import('./pages/WorkflowEditor'))
const Library = lazy(() => import('./pages/Library'))
const Chat = lazy(() => import('./pages/Chat'))
const Admin = lazy(() => import('./pages/Admin'))
const Account = lazy(() => import('./pages/Account'))
const Automation = lazy(() => import('./pages/Automation'))
const Office = lazy(() => import('./pages/Office'))
const BrowserAutomation = lazy(() => import('./pages/BrowserAutomation'))
const Spaces = lazy(() => import('./pages/Spaces'))
const Verification = lazy(() => import('./pages/Verification'))
const Docs = lazy(() => import('./pages/Docs'))
const Demo = lazy(() => import('./pages/Demo'))
const DemoFeedback = lazy(() => import('./pages/DemoFeedback'))

// ---------------------------------------------------------------------------
// Route tree
// ---------------------------------------------------------------------------

const rootRoute = createRootRoute({
  component: () => (
    <Suspense fallback={<div className="p-6 text-gray-500 text-sm">Loading...</div>}>
      <Outlet />
    </Suspense>
  ),
})

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/landing',
  validateSearch: (search: Record<string, unknown>) => ({
    error: (search.error as string) || undefined,
  }),
  component: Landing,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: () => <Navigate to="/landing" />,
})

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/register',
  component: () => <Navigate to="/landing" />,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  validateSearch: (search: Record<string, unknown>) => ({
    // Workspace mode (chat is the default, omitted from URL when active)
    mode: (['chat', 'files', 'automations', 'knowledge'].includes(search.mode as string)
      ? (search.mode as 'chat' | 'files' | 'automations' | 'knowledge')
      : undefined),
    // Active right panel tab (assistant is the default, omitted when active)
    tab: (['assistant', 'library'].includes(search.tab as string)
      ? (search.tab as 'assistant' | 'library')
      : undefined),
    // Open editor IDs — support legacy param names for backwards compat
    workflow: ((search.workflow as string) || (search.openWorkflow as string) || undefined),
    extraction: ((search.extraction as string) || (search.openExtraction as string) || undefined),
    automation: (search.automation as string) || undefined,
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

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: () => (
    <ProtectedRoute>
      <Chat />
    </ProtectedRoute>
  ),
})

const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/library',
  component: () => (
    <ProtectedRoute>
      <Library />
    </ProtectedRoute>
  ),
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

const officeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/office',
  component: () => (
    <ProtectedRoute>
      <Office />
    </ProtectedRoute>
  ),
})

const browserAutomationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/browser-automation',
  component: () => (
    <ProtectedRoute>
      <BrowserAutomation />
    </ProtectedRoute>
  ),
})

const spacesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/spaces',
  component: () => (
    <ProtectedRoute>
      <Spaces />
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

const docsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/docs',
  component: Docs,
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

const demoStatusRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/demo/status/$uuid',
  component: Demo,
})

const routeTree = rootRoute.addChildren([
  landingRoute,
  loginRoute,
  registerRoute,
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
  spacesRoute,
  verificationRoute,
  docsRoute,
  demoRoute,
  demoFeedbackRoute,
  demoStatusRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
