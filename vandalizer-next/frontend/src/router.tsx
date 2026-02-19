import { lazy, Suspense } from 'react'
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from '@tanstack/react-router'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Workspace } from './pages/Workspace'
import { TeamSettings } from './pages/TeamSettings'

const Workflows = lazy(() => import('./pages/Workflows'))
const WorkflowEditor = lazy(() => import('./pages/WorkflowEditor'))
const Library = lazy(() => import('./pages/Library'))
const Chat = lazy(() => import('./pages/Chat'))
const Admin = lazy(() => import('./pages/Admin'))
const Account = lazy(() => import('./pages/Account'))
const Automation = lazy(() => import('./pages/Automation'))
const Office = lazy(() => import('./pages/Office'))
const BrowserAutomation = lazy(() => import('./pages/BrowserAutomation'))

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

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: Login,
})

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/register',
  component: Register,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  validateSearch: (search: Record<string, unknown>) => ({
    openWorkflow: (search.openWorkflow as string) || undefined,
    openExtraction: (search.openExtraction as string) || undefined,
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

const routeTree = rootRoute.addChildren([
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
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
