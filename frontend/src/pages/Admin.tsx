import { lazy, Suspense, useEffect, useState } from 'react'
import {
  Shield, ShieldCheck, BarChart3, Users, Building2, Workflow, Settings,
  Lock, Globe, Zap,
  FileText, FolderTree,
  Mail, Award, KeyRound, PackageOpen,
  BookOpen, Sparkles,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { getAuthConfig } from '../api/auth'
import { UpdateBanner } from '../components/admin/UpdateBanner'
import { CatalogUpdateBanner } from '../components/admin/CatalogUpdateBanner'
import { UsageTab } from '../components/admin/UsageTab'
import { TelemetryOptInBanner } from '../components/admin/TelemetryOptInBanner'
import { getFeatureFlags } from '../api/config'

// UsageTab is the default `activeTab` (see useState<Tab>('usage') below), so it
// stays a static import to avoid an extra network round-trip before the admin
// landing view paints. Every other tab is lazy-loaded — most admins only ever
// see a handful of these, and the rest (e.g. ConfigTab, DemoTab) are large.
const CatalogTab = lazy(() => import('../components/admin/CatalogTab').then(m => ({ default: m.CatalogTab })))
const ApiKeysTab = lazy(() => import('../components/admin/ApiKeysTab').then(m => ({ default: m.ApiKeysTab })))
const ComplianceTab = lazy(() => import('../components/admin/ComplianceTab').then(m => ({ default: m.ComplianceTab })))
const TeamsTab = lazy(() => import('../components/admin/TeamsTab').then(m => ({ default: m.TeamsTab })))
const KnowledgeBasesTab = lazy(() => import('../components/admin/KnowledgeBasesTab').then(m => ({ default: m.KnowledgeBasesTab })))
const AuditTab = lazy(() => import('../components/admin/AuditTab').then(m => ({ default: m.AuditTab })))
const UsersTab = lazy(() => import('../components/admin/UsersTab').then(m => ({ default: m.UsersTab })))
const WorkflowsTab = lazy(() => import('../components/admin/WorkflowsTab').then(m => ({ default: m.WorkflowsTab })))
const OrganizationsTab = lazy(() => import('../components/admin/OrganizationsTab').then(m => ({ default: m.OrganizationsTab })))
const QualityTab = lazy(() => import('../components/admin/QualityTab').then(m => ({ default: m.QualityTab })))
const OptimizerTab = lazy(() => import('../components/admin/OptimizerTab').then(m => ({ default: m.OptimizerTab })))
const CertificationsTab = lazy(() => import('../components/admin/CertificationsTab').then(m => ({ default: m.CertificationsTab })))
const EmailAnalyticsTab = lazy(() => import('../components/admin/EmailAnalyticsTab').then(m => ({ default: m.EmailAnalyticsTab })))
const DemoTab = lazy(() => import('../components/admin/DemoTab').then(m => ({ default: m.DemoTab })))
const TelemetryTab = lazy(() => import('../components/admin/TelemetryTab').then(m => ({ default: m.TelemetryTab })))
const ConfigTab = lazy(() => import('../components/admin/ConfigTab').then(m => ({ default: m.ConfigTab })))

type Tab = 'usage' | 'users' | 'teams' | 'organizations' | 'workflows' | 'quality' | 'optimizer' | 'knowledgebases' | 'compliance' | 'audit' | 'demo' | 'email' | 'certifications' | 'apikeys' | 'catalog' | 'telemetry' | 'config'

// Minimum role that may see a tab: 'admin' satisfies everything, 'staff'
// satisfies 'staff' and 'teamAdmin', 'teamAdmin' satisfies only 'teamAdmin'.
// See AUTHORIZATION_MATRIX.md for the server-side model this mirrors — this
// list is a UX affordance, never the enforcement boundary; every admin route
// fails closed independently regardless of what this predicate decides.
type MinRole = 'teamAdmin' | 'staff' | 'admin'

interface TabDef {
  key: Tab
  label: string
  icon: typeof BarChart3
  minRole: MinRole
  requires?: 'trial' | 'telemetryCollector'
}

const TABS: TabDef[] = [
  { key: 'usage', label: 'Usage', icon: BarChart3, minRole: 'teamAdmin' },
  { key: 'users', label: 'Users', icon: Users, minRole: 'teamAdmin' },
  { key: 'teams', label: 'Teams', icon: Building2, minRole: 'staff' },
  { key: 'organizations', label: 'Organizations', icon: FolderTree, minRole: 'staff' },
  { key: 'workflows', label: 'Workflows', icon: Workflow, minRole: 'teamAdmin' },
  { key: 'quality', label: 'Quality', icon: ShieldCheck, minRole: 'staff' },
  { key: 'optimizer', label: 'Optimizer', icon: Sparkles, minRole: 'staff' },
  { key: 'knowledgebases', label: 'Knowledge Bases', icon: BookOpen, minRole: 'staff' },
  { key: 'compliance', label: 'Compliance', icon: Lock, minRole: 'staff' },
  { key: 'audit', label: 'Audit Log', icon: FileText, minRole: 'staff' },
  { key: 'demo', label: 'Demo', icon: Zap, minRole: 'staff', requires: 'trial' },
  { key: 'email', label: 'Email', icon: Mail, minRole: 'staff' },
  { key: 'certifications', label: 'Certifications', icon: Award, minRole: 'staff' },
  { key: 'apikeys', label: 'API Keys', icon: KeyRound, minRole: 'staff' },
  { key: 'catalog', label: 'Catalog', icon: PackageOpen, minRole: 'admin' },
  { key: 'telemetry', label: 'Telemetry', icon: Globe, minRole: 'staff', requires: 'telemetryCollector' },
  { key: 'config', label: 'Config', icon: Settings, minRole: 'admin' },
]

// ──────────────────────────────────────────
// Main Admin Component
// ──────────────────────────────────────────

export default function Admin() {
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const [activeTab, setActiveTab] = useState<Tab>('usage')
  const [trialEnabled, setTrialEnabled] = useState(false)
  // Only true on the fleet collector instance; hides the Telemetry tab elsewhere.
  const [telemetryCollector, setTelemetryCollector] = useState(false)

  useEffect(() => {
    getAuthConfig().then(c => setTrialEnabled(!!c.trial_system_enabled)).catch(() => {})
    getFeatureFlags().then(f => setTelemetryCollector(!!f.telemetry_collector_enabled)).catch(() => {})
  }, [])

  const isGlobalAdmin = !!user?.is_admin
  const isStaff = !!user?.is_staff
  const isTeamAdmin = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  // Examiners are intentionally excluded: every admin-panel endpoint gates on
  // admin/staff/team-admin (see _require_admin_or_team_admin), so examiners would
  // only hit 403s here. Their workspace is the Verification queue (/verification).
  const hasAccess = isGlobalAdmin || isStaff || isTeamAdmin

  // Single source of truth for tab visibility: role satisfies the tab's
  // minRole, and any feature-flag requirement is met. Used for both the
  // sidebar filter and the render guards below so the two cannot disagree.
  const canSee = (t: TabDef): boolean => {
    const roleOk = isGlobalAdmin
      || (isStaff && (t.minRole === 'staff' || t.minRole === 'teamAdmin'))
      || (isTeamAdmin && t.minRole === 'teamAdmin')
    if (!roleOk) return false
    if (t.requires === 'trial' && !trialEnabled) return false
    if (t.requires === 'telemetryCollector' && !telemetryCollector) return false
    return true
  }

  const visibleTabs = TABS.filter(canSee)
  // O(1) lookup so render guards can apply `canSee` to a specific tab by key
  // without re-scanning TABS on every render.
  const tabByKey = Object.fromEntries(TABS.map(t => [t.key, t])) as Record<Tab, TabDef>

  // Honor ?tab=<key> deep links (e.g. the catalog-update notification). Only a
  // tab the current user can actually see is honored — an unreachable request
  // (e.g. ?tab=config for a team admin) leaves activeTab at its default
  // instead of landing on a tab whose content is fully gated (a blank pane).
  // The effect re-runs whenever visibility recomputes (so a flag-gated tab
  // like ?tab=demo can still be honored once its flag resolves), which is why
  // applying must be one-shot: the param is dropped from the URL on apply, or
  // every later re-run would yank the user back to the deep-linked tab.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const requested = params.get('tab')
    if (requested && visibleTabs.some(t => t.key === requested)) {
      setActiveTab(requested as Tab)
      params.delete('tab')
      const qs = params.toString()
      window.history.replaceState(
        window.history.state, '',
        window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash,
      )
    }
  }, [visibleTabs])

  // If the active tab is ever not visible (e.g. feature flags resolve after
  // mount and hide it), fall back to the first visible tab for rendering
  // purposes only — a derived value, not stored state, so there is no setState
  // loop. Clicking a sidebar entry still sets `activeTab` directly since only
  // visible tabs are ever rendered as clickable.
  const effectiveActiveTab: Tab = visibleTabs.some(t => t.key === activeTab)
    ? activeTab
    : (visibleTabs[0]?.key ?? activeTab)

  if (!hasAccess) {
    return (
      <PageLayout>
        <div style={{ maxWidth: 480, margin: '60px auto', textAlign: 'center' }}>
          <Shield size={40} color="#d1d5db" style={{ marginBottom: 16 }} />
          <h2 style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>Access Denied</h2>
          <p style={{ fontSize: 14, color: '#6b7280', marginTop: 8 }}>
            You must be a team admin or system administrator to view this page.
          </p>
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div style={{ display: 'flex', gap: 0, minHeight: 'calc(100vh - 130px)' }}>
        {/* Sidebar */}
        <nav aria-label="Admin sections" style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid #e5e7eb',
          backgroundColor: '#fff',
          padding: '20px 0',
          borderRadius: 'var(--ui-radius, 12px) 0 0 var(--ui-radius, 12px)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', marginBottom: 20 }}>
            <Shield size={20} color="#6b7280" />
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>
              {isGlobalAdmin || isStaff ? 'Admin' : 'Team Admin'}
            </h1>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px' }}>
            {visibleTabs.map(tab => {
              const Icon = tab.icon
              const isActive = effectiveActiveTab === tab.key
              return (
                <button
                  key={tab.key}
                  type="button"
                  aria-current={isActive ? 'page' : undefined}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px', border: 'none', cursor: 'pointer',
                    fontSize: 14, fontWeight: isActive ? 600 : 400,
                    color: isActive ? '#111827' : '#6b7280',
                    backgroundColor: isActive ? '#f3f4f6' : 'transparent',
                    borderRadius: 8, fontFamily: 'inherit',
                    transition: 'background-color 0.15s, color 0.15s',
                    width: '100%', textAlign: 'left',
                    borderLeft: isActive ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
                  }}
                >
                  <Icon size={18} style={{ flexShrink: 0 }} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </nav>

        {/* Content */}
        <div style={{ flex: 1, padding: '20px 32px', minWidth: 0 }}>
          <UpdateBanner />
          {isGlobalAdmin && <CatalogUpdateBanner onView={() => setActiveTab('catalog')} />}
          {isGlobalAdmin && <TelemetryOptInBanner />}
          <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>}>
            {effectiveActiveTab === 'usage' && canSee(tabByKey.usage) && <UsageTab />}
            {effectiveActiveTab === 'users' && canSee(tabByKey.users) && <UsersTab />}
            {effectiveActiveTab === 'teams' && canSee(tabByKey.teams) && <TeamsTab />}
            {effectiveActiveTab === 'organizations' && canSee(tabByKey.organizations) && <OrganizationsTab />}
            {effectiveActiveTab === 'workflows' && canSee(tabByKey.workflows) && <WorkflowsTab />}
            {effectiveActiveTab === 'quality' && canSee(tabByKey.quality) && <QualityTab />}
            {effectiveActiveTab === 'optimizer' && canSee(tabByKey.optimizer) && <OptimizerTab />}
            {effectiveActiveTab === 'knowledgebases' && canSee(tabByKey.knowledgebases) && <KnowledgeBasesTab canEdit={isGlobalAdmin} />}
            {effectiveActiveTab === 'compliance' && canSee(tabByKey.compliance) && <ComplianceTab />}
            {effectiveActiveTab === 'audit' && canSee(tabByKey.audit) && <AuditTab />}
            {effectiveActiveTab === 'demo' && canSee(tabByKey.demo) && <DemoTab />}
            {effectiveActiveTab === 'email' && canSee(tabByKey.email) && <EmailAnalyticsTab />}
            {effectiveActiveTab === 'certifications' && canSee(tabByKey.certifications) && <CertificationsTab />}
            {effectiveActiveTab === 'apikeys' && canSee(tabByKey.apikeys) && <ApiKeysTab />}
            {effectiveActiveTab === 'catalog' && canSee(tabByKey.catalog) && <CatalogTab />}
            {effectiveActiveTab === 'telemetry' && canSee(tabByKey.telemetry) && <TelemetryTab />}
            {effectiveActiveTab === 'config' && canSee(tabByKey.config) && <ConfigTab />}
          </Suspense>
        </div>
      </div>
    </PageLayout>
  )
}
