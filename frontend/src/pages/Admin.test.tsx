import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render as renderView, screen, within, waitFor, fireEvent } from '@testing-library/react'
import Admin from './Admin'
import { createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { useState, type ReactElement } from 'react'
const render = (view: ReactElement) => {
  const root = createRootRoute()
  const route = createRoute({ getParentRoute: () => root, path: '/admin', validateSearch: (search: Record<string, unknown>) => ({ tab: typeof search.tab === 'string' ? search.tab : undefined }), component: () => view })
  const router = createRouter({ routeTree: root.addChildren([route]) })
  return renderView(<RouterProvider router={router} />)
}

// ---------------------------------------------------------------------------
// This suite is the behavior-preservation proof for plan 008: it verifies the
// derived `canSee` predicate reproduces the exact truth table the old
// `hiddenForNonAdmin` array + three-way branch used to encode (17 / 15 / 3
// tabs for admin / staff / team-admin, including the Optimizer tab added on
// main), and that the `?tab=` deep link no longer lands on a tab whose
// content is fully gated.
//
// Tab components are stubbed to trivial text so assertions are about
// visibility, not tab internals. Several tabs are lazy-loaded (see Admin.tsx),
// so `screen.findBy*` / `waitFor` is used wherever we assert on tab *content*.
// ---------------------------------------------------------------------------

interface MockUser {
  is_admin?: boolean
  is_staff?: boolean
}

interface MockTeam {
  role?: string
}

let mockUser: MockUser | null = null
let mockCurrentTeam: MockTeam | null = null

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: mockUser }),
}))

vi.mock('../hooks/useTeams', () => ({
  useTeams: () => ({ currentTeam: mockCurrentTeam }),
}))

const mockGetAuthConfig = vi.fn()
const mockGetFeatureFlags = vi.fn()

vi.mock('../api/auth', () => ({
  getAuthConfig: (...args: unknown[]) => mockGetAuthConfig(...args),
}))

vi.mock('../api/config', () => ({
  getFeatureFlags: (...args: unknown[]) => mockGetFeatureFlags(...args),
}))

vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../components/admin/UpdateBanner', () => ({
  UpdateBanner: () => null,
}))
vi.mock('../components/admin/CatalogUpdateBanner', () => ({
  CatalogUpdateBanner: () => null,
}))
vi.mock('../components/admin/TelemetryOptInBanner', () => ({
  TelemetryOptInBanner: () => null,
}))

vi.mock('../components/admin/UsageTab', () => ({
  UsageTab: () => <div>UsageTab Stub</div>,
}))
vi.mock('../components/admin/UsersTab', () => ({
  UsersTab: () => <div>UsersTab Stub</div>,
}))
vi.mock('../components/admin/TeamsTab', () => ({
  TeamsTab: () => <div>TeamsTab Stub</div>,
}))
vi.mock('../components/admin/OrganizationsTab', () => ({
  OrganizationsTab: () => <div>OrganizationsTab Stub</div>,
}))
vi.mock('../components/admin/WorkflowsTab', () => ({
  WorkflowsTab: () => <div>WorkflowsTab Stub</div>,
}))
vi.mock('../components/admin/QualityTab', () => ({
  QualityTab: () => <div>QualityTab Stub</div>,
}))
vi.mock('../components/admin/OptimizerTab', () => ({
  OptimizerTab: () => <div>OptimizerTab Stub</div>,
}))
vi.mock('../components/admin/KnowledgeBasesTab', () => ({
  KnowledgeBasesTab: () => <div>KnowledgeBasesTab Stub</div>,
}))
vi.mock('../components/admin/ComplianceTab', () => ({
  ComplianceTab: () => <div>ComplianceTab Stub</div>,
}))
vi.mock('../components/admin/AuditTab', () => ({
  AuditTab: () => <div>AuditTab Stub</div>,
}))
vi.mock('../components/admin/DemoTab', () => ({
  DemoTab: () => <div>DemoTab Stub</div>,
}))
vi.mock('../components/admin/EmailAnalyticsTab', () => ({
  EmailAnalyticsTab: () => <div>EmailAnalyticsTab Stub</div>,
}))
vi.mock('../components/admin/CertificationsTab', () => ({
  CertificationsTab: () => <div>CertificationsTab Stub</div>,
}))
vi.mock('../components/admin/ApiKeysTab', () => ({
  ApiKeysTab: () => <div>ApiKeysTab Stub</div>,
}))
vi.mock('../components/admin/CatalogTab', () => ({
  CatalogTab: () => <div>CatalogTab Stub</div>,
}))
vi.mock('../components/admin/TelemetryTab', () => ({
  TelemetryTab: () => <div>TelemetryTab Stub</div>,
}))
vi.mock('../components/admin/ConfigTab', () => ({
  ConfigTab: () => <div>ConfigTab Stub</div>,
}))

const ALL_17_LABELS = [
  'Usage', 'Users', 'Teams', 'Organizations', 'Workflows', 'Quality',
  'Optimizer', 'Knowledge Bases', 'Compliance', 'Audit Log', 'Demo', 'Email',
  'Certifications', 'API Keys', 'Catalog', 'Telemetry', 'Config',
]

function getSidebarLabels(): string[] {
  const nav = screen.getByRole('navigation', { name: 'Admin sections' })
  return within(nav).getAllByRole('button').map(btn => btn.textContent?.trim() ?? '')
}

beforeEach(() => {
  mockUser = null
  mockCurrentTeam = null
  mockGetAuthConfig.mockReset().mockResolvedValue({ trial_system_enabled: true })
  mockGetFeatureFlags.mockReset().mockResolvedValue({ telemetry_collector_enabled: true })
  window.history.pushState({}, '', '/admin')
})

describe('Admin — tab visibility truth table', () => {
  it('1. is_admin with both flags on sees all 17 tabs', async () => {
    mockUser = { is_admin: true, is_staff: false }
    render(<Admin />)
    await waitFor(() => expect(getSidebarLabels()).toHaveLength(17))
    expect(getSidebarLabels()).toEqual(ALL_17_LABELS)
  })

  it('2. is_staff (not admin) with both flags on sees 15; config and catalog absent', async () => {
    mockUser = { is_admin: false, is_staff: true }
    render(<Admin />)
    await waitFor(() => expect(getSidebarLabels()).toHaveLength(15))
    const labels = getSidebarLabels()
    expect(labels).not.toContain('Config')
    expect(labels).not.toContain('Catalog')
  })

  it('3. team admin (owner/admin role, neither platform flag) sees exactly 3: Usage, Users, Workflows', async () => {
    mockUser = { is_admin: false, is_staff: false }
    mockCurrentTeam = { role: 'admin' }
    render(<Admin />)
    await waitFor(() => expect(getSidebarLabels()).toHaveLength(3))
    expect(getSidebarLabels()).toEqual(['Usage', 'Users', 'Workflows'])
  })

  it('4. trialEnabled: false hides Demo for an admin who would otherwise see it', async () => {
    mockUser = { is_admin: true, is_staff: false }
    mockGetAuthConfig.mockResolvedValue({ trial_system_enabled: false })
    render(<Admin />)
    await waitFor(() => expect(getSidebarLabels()).toHaveLength(16))
    expect(getSidebarLabels()).not.toContain('Demo')
  })

  it('5. telemetryCollector: false hides Telemetry for an admin', async () => {
    mockUser = { is_admin: true, is_staff: false }
    mockGetFeatureFlags.mockResolvedValue({ telemetry_collector_enabled: false })
    render(<Admin />)
    await waitFor(() => expect(getSidebarLabels()).toHaveLength(16))
    expect(getSidebarLabels()).not.toContain('Telemetry')
  })

  it('6. neither admin/staff nor team admin sees Access Denied, no tab list', async () => {
    mockUser = { is_admin: false, is_staff: false }
    mockCurrentTeam = { role: 'member' }
    render(<Admin />)
    expect(await screen.findByText('Access Denied')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Admin sections' })).not.toBeInTheDocument()
  })

  it('7. ?tab=config as team admin does not render ConfigTab, and does not leave a blank pane', async () => {
    mockUser = { is_admin: false, is_staff: false }
    mockCurrentTeam = { role: 'owner' }
    window.history.pushState({}, '', '/admin?tab=config')
    render(<Admin />)
    // A usable tab (the default, Usage) renders instead of a blank pane.
    expect(await screen.findByText('UsageTab Stub')).toBeInTheDocument()
    expect(screen.queryByText('ConfigTab Stub')).not.toBeInTheDocument()
  })

  it('8. after a ?tab= deep link is applied, clicking another tab navigates away and stays there', async () => {
    mockUser = { is_admin: true, is_staff: false }
    window.history.pushState({}, '', '/admin?tab=catalog')
    render(<Admin />)
    // Deep link is honored first…
    expect(await screen.findByText('CatalogTab Stub')).toBeInTheDocument()
    // The section remains in the URL so refresh can restore it.
    expect(new URLSearchParams(window.location.search).get('tab')).toBe('catalog')

    fireEvent.click(within(screen.getByRole('navigation', { name: 'Admin sections' })).getByRole('button', { name: 'Users' }))
    expect(await screen.findByText('UsersTab Stub')).toBeInTheDocument()
    expect(screen.queryByText('CatalogTab Stub')).not.toBeInTheDocument()
    expect(new URLSearchParams(window.location.search).get('tab')).toBe('users')
  })
})


it('re-evaluates an open privileged section when platform and team permissions change', async () => {
  mockUser = { is_admin: true, is_staff: false }
  mockCurrentTeam = { role: 'owner' }
  window.history.pushState({}, '', '/admin?tab=config')
  function ChangingPermissions() {
    const [, setRevision] = useState(0)
    return <>
      <button onClick={() => { mockUser = { is_admin: false, is_staff: false }; setRevision(v => v + 1) }}>Remove platform role</button>
      <button onClick={() => { mockCurrentTeam = { role: 'member' }; setRevision(v => v + 1) }}>Switch to member team</button>
      <Admin />
    </>
  }
  render(<ChangingPermissions />)
  expect(await screen.findByText('ConfigTab Stub')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Remove platform role' }))
  expect(await screen.findByText('UsageTab Stub')).toBeInTheDocument()
  expect(screen.queryByText('ConfigTab Stub')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Switch to member team' }))
  expect(await screen.findByText('Access Denied')).toBeInTheDocument()
  expect(screen.queryByText('UsageTab Stub')).not.toBeInTheDocument()
})
