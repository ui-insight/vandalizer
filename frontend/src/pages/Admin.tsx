import { useNavigate, useSearch } from '@tanstack/react-router'
import { SectionPage } from '../components/layout/SectionPage'
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
  const search = useSearch({ from: '/admin' })
  const navigate = useNavigate()
  const activeTab = (search.tab || 'usage') as Tab
  const setActiveTab = (tab: Tab) => { void navigate({ to: '/admin', search: { tab } }) }
  const [trialEnabled, setTrialEnabled] = useState(false)
  // Only true on the fleet collector instance; hides the Telemetry tab elsewhere.
  const [telemetryCollector, setTelemetryCollector] = useState(false)
  const [featuresLoading, setFeaturesLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([getAuthConfig(), getFeatureFlags()]).then(([auth, features]) => {
      if (cancelled) return
      if (auth.status === 'fulfilled') setTrialEnabled(!!auth.value.trial_system_enabled)
      if (features.status === 'fulfilled') setTelemetryCollector(!!features.value.telemetry_collector_enabled)
      setFeaturesLoading(false)
    })
    return () => { cancelled = true }
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

  // The URL owns the section so refresh, shared links and browser Back/Forward
  // restore it. Rendering still checks the current role and feature flags.
  // If the active tab is ever not visible (e.g. feature flags resolve after
  // mount and hide it), fall back to the first visible tab for rendering
  // purposes only — a derived value, not stored state, so there is no setState
  // loop. Clicking a sidebar entry still sets `activeTab` directly since only
  // visible tabs are ever rendered as clickable.
  const waitingForFeature = featuresLoading && !!tabByKey[activeTab]?.requires
  const effectiveActiveTab: Tab = waitingForFeature || visibleTabs.some(t => t.key === activeTab)
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
      <SectionPage title={isGlobalAdmin || isStaff ? 'Admin' : 'Team Admin'} icon={Shield} label="Admin sections" sections={visibleTabs} active={effectiveActiveTab} onSelect={setActiveTab}>
          <UpdateBanner />
          {isGlobalAdmin && <CatalogUpdateBanner onView={() => setActiveTab('catalog')} />}
          {isGlobalAdmin && <TelemetryOptInBanner />}
          <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>}>
            {waitingForFeature && <p role="status">Loading section availability…</p>}
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
      </SectionPage>
    </PageLayout>
  )
}
