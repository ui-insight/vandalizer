import { WorkspaceSectionHeader } from '../shared/WorkspaceSectionHeader'
import { useEffect, useMemo, useState } from 'react'
import { CalendarClock, FolderKanban, FolderSearch, Globe, HelpCircle, Loader2, Mail, Pin, PinOff, Plus, Search, X } from 'lucide-react'
import { AutomationsExplainer } from './AutomationsExplainer'
import { AutomationCreationWizard } from './AutomationCreationWizard'
import { AutomationSummary } from './AutomationSummary'
import { useAutomationFolderNames } from '../../hooks/useAutomationFolderNames'
import { useAutomations } from '../../hooks/useAutomations'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useSearchSets } from '../../hooks/useExtractions'
import { useProjectPins } from '../../hooks/useProjectPins'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { getFeatureFlags } from '../../api/config'
import type { Automation, TriggerType } from '../../types/automation'
import { formatRunTime } from '../../utils/schedule'

const TRIGGER_BADGES: Record<TriggerType, { label: string }> = {
  folder_watch: { label: 'Folder Watch' },
  api: { label: 'API' },
  m365_intake: { label: 'M365' },
  schedule: { label: 'Schedule' },
}

type FilterMode = 'all' | 'folder_watch' | 'api' | 'schedule' | 'm365_intake'

export function AutomationsPanel({ activeIds = new Set<string>() }: { activeIds?: Set<string> }) {
  const { openAutomation, openAutomationId, activeProjectUuid, activeProjectTitle, activeProjectRole } = useWorkspace()
  const { automations, loading, error, refresh } = useAutomations()
  const folderNames = useAutomationFolderNames()
  const { workflows } = useWorkflows()
  const { searchSets } = useSearchSets()
  const projectPins = useProjectPins(activeProjectUuid)

  const [filter, setFilter] = useState<FilterMode>('all')
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)
  const [showExplainer, setShowExplainer] = useState(false)
  const [m365Enabled, setM365Enabled] = useState(false)
  // When inside a project, default to showing only the automations pinned to it.
  // The "Show all" toggle escapes the scope; reset to scoped when the project changes.
  const [projectScoped, setProjectScoped] = useState(true)
  useEffect(() => { setProjectScoped(true) }, [activeProjectUuid])

  const canPin = !!activeProjectUuid && activeProjectRole !== 'viewer'

  useEffect(() => {
    getFeatureFlags().then(f => setM365Enabled(f.m365_enabled)).catch(() => {})
  }, [])

  // Refresh list when editor saves or closes
  useEffect(() => {
    if (openAutomationId === null) void refresh()
    const handler = () => refresh()
    window.addEventListener('automations-updated', handler)
    return () => window.removeEventListener('automations-updated', handler)
  }, [openAutomationId, refresh])

  // The base list reflects the project scope: when scoped, only automations
  // pinned to the active project. Everything below (counts, type filter, search)
  // narrows this base, so the type-filter counts stay honest within the scope.
  const isProjectScoped = !!activeProjectUuid && projectScoped
  const base = useMemo(() => {
    if (!isProjectScoped) return automations
    const pinned = projectPins.idsByType('automation')
    return automations.filter(a => pinned.has(a.id))
  }, [automations, isProjectScoped, projectPins])

  const filtered = useMemo(() => {
    let list = base
    if (filter !== 'all') list = list.filter(a => a.trigger_type === filter)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) ||
        (a.description || '').toLowerCase().includes(q),
      )
    }
    return list
  }, [base, filter, search])

  const counts = useMemo(() => ({
    all: base.length,
    folder_watch: base.filter(a => a.trigger_type === 'folder_watch').length,
    api: base.filter(a => a.trigger_type === 'api').length,
    schedule: base.filter(a => a.trigger_type === 'schedule').length,
    m365_intake: base.filter(a => a.trigger_type === 'm365_intake').length,
  }), [base])

  const scopeLoading = isProjectScoped && projectPins.loading
  const listError = error || (isProjectScoped ? projectPins.error : null)
  const clearFilters = () => { setSearch(''); setFilter('all') }

  const togglePin = async (e: React.MouseEvent, autoId: string) => {
    e.stopPropagation()
    try {
      if (projectPins.isPinned('automation', autoId)) await projectPins.unpin('automation', autoId)
      else await projectPins.pin('automation', autoId)
    } catch { /* ignore — surfaced by absence of the pin toggling */ }
  }

  const getActionName = (auto: Automation) => auto.action_type === 'extraction'
    ? searchSets.find(item => item.uuid === auto.action_id || item.id === auto.action_id)?.title
    : workflows.find(item => item.id === auto.action_id)?.name

  return (
    <div className="automations-panel automation-surface" style={{ height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--workspace-canvas)' }}>
      <WorkspaceSectionHeader title="Automations" help={<ExplainerPill tone="light" label="What are automations?" onClick={() => setShowExplainer(true)} />} actions={
        <button
          onClick={() => setShowWizard(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--workspace-space-6)',
            padding: "var(--workspace-space-6) var(--workspace-space-16)",
            fontSize: 'var(--workspace-font-control)',
            fontWeight: 600,
            fontFamily: 'inherit',
            color: 'var(--highlight-text-color, #000)',
            backgroundColor: 'var(--highlight-color, #eab308)',
            border: 'none',
            borderRadius: 'var(--workspace-radius-small)',
            cursor: 'pointer',
          }}
        >
          <Plus style={{ width: 14, height: 14 }} />
          New
        </button>      } />

      {/* Project scope bar — only inside a project. Lets you flip between the
          automations pinned to this project and the whole workspace. */}
      {activeProjectUuid && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)',
          padding: "7px var(--workspace-space-12)",
          backgroundColor: 'var(--workspace-surface)',
          borderBottom: '1px solid var(--workspace-border)',
          flexShrink: 0,
        }}>
          <FolderKanban size={13} style={{ color: 'var(--highlight-on-light)', flexShrink: 0 }} />
          <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'normal' }}>
            {projectScoped
              ? <>Pinned to <strong style={{ color: 'var(--workspace-text)' }}>{activeProjectTitle}</strong></>
              : <>All automations</>}
          </span>
          <button
            onClick={() => setProjectScoped(s => !s)}
            style={{
              marginLeft: 'auto', flexShrink: 0,
              padding: "var(--workspace-space-4) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--workspace-text)', backgroundColor: 'transparent',
              border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-large)', cursor: 'pointer',
            }}
          >
            {projectScoped ? 'Show all' : 'Show project only'}
          </button>
        </div>
      )}

      {/* Filter bar */}
      {(base.length > 0 || search || filter !== 'all') && (
        <div style={{
          display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--workspace-space-6)',
          padding: "var(--workspace-space-8) var(--workspace-space-12)",
          backgroundColor: 'var(--workspace-canvas)',
          borderBottom: '1px solid var(--workspace-border)',
          flexShrink: 0,
        }}>
          <FilterPill label="All" count={counts.all} active={filter === 'all'} onClick={() => setFilter('all')} />
          <FilterPill label="Folder Watch" count={counts.folder_watch} active={filter === 'folder_watch'} onClick={() => setFilter('folder_watch')} icon={<FolderSearch size={10} />} />
          <FilterPill label="API" count={counts.api} active={filter === 'api'} onClick={() => setFilter('api')} icon={<Globe size={10} />} />
          {(counts.schedule > 0 || filter === 'schedule') && <FilterPill label="Schedule" count={counts.schedule} active={filter === 'schedule'} onClick={() => setFilter('schedule')} icon={<CalendarClock size={10} />} />}
          {(m365Enabled || counts.m365_intake > 0 || filter === 'm365_intake') && <FilterPill label="M365" count={counts.m365_intake} active={filter === 'm365_intake'} onClick={() => setFilter('m365_intake')} icon={<Mail size={10} />} />}
          <div style={{ flex: 1 }} />
          <div style={{
            display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)',
            padding: "0 var(--workspace-space-12)", minHeight: 'var(--workspace-control-height)', order: -1, flexBasis: '100%',
            backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
            minWidth: 0,
          }}>
            <Search size={16} style={{ color: '#555', flexShrink: 0 }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter..."
              aria-label="Filter automations"
              style={{
                flex: 1, minWidth: 0, padding: 0, fontSize: 'var(--workspace-font-body)', fontFamily: 'inherit',
                color: 'var(--workspace-text)', backgroundColor: 'transparent',
                border: 'none', outline: 'none',
              }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="Clear filter"
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}
              >
                <X size={10} style={{ color: '#555' }} />
              </button>
            )}
          </div>
        </div>
      )}

      {(search || filter !== 'all') && (
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--workspace-space-8)', padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
          {!loading && !scopeLoading && !listError && <span role="status">{filtered.length} of {base.length} automations</span>}
          <button type="button" onClick={clearFilters} style={{ color: 'var(--workspace-text)', border: '1px solid #6b7280', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)" }}>Clear filters</button>
        </div>
      )}
      {folderNames.error && <div className="automation-folder-error" role="status">Folder names are unavailable. <button type="button" onClick={() => void folderNames.refresh()}>Retry folder names</button></div>}
      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-12) var(--workspace-space-12)", position: 'relative' }}>
      {listError && (
        <div role="alert" style={{ margin: 'var(--workspace-space-12)', padding: 'var(--workspace-space-12)', border: '1px solid #fca5a5', borderRadius: 'var(--workspace-radius-medium)', color: '#b91c1c', fontSize: 'var(--workspace-font-control)' }}>
          <p>{listError}</p>
          <p>{base.length ? 'Showing the previously loaded list. Your filters are preserved.' : 'The list is unavailable. Your filters are preserved.'}</p>
          <button type="button" onClick={() => { void refresh(); if (isProjectScoped) void projectPins.refresh() }} style={{ marginTop: 'var(--workspace-space-8)', color: 'var(--workspace-text)', border: '1px solid #9ca3af', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)" }}>Retry automations</button>
        </div>
      )}

        {(loading || scopeLoading) && base.length === 0 ? (
          <div role="status" aria-live="polite" aria-label="Loading automations" style={{ textAlign: 'center', padding: 40, color: 'var(--workspace-muted)' }}>
            <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : listError && base.length === 0 ? null : base.length === 0 && isProjectScoped && automations.length > 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--workspace-muted)', fontSize: 'var(--workspace-font-control)' }}>
            <FolderKanban size={28} style={{ color: '#444', margin: "0 auto var(--workspace-space-12)" }} />
            <div style={{ color: 'var(--workspace-text)', fontWeight: 600, marginBottom: 'var(--workspace-space-4)' }}>No automations pinned to this project</div>
            <div style={{ marginBottom: 'var(--workspace-space-16)' }}>Pin an automation to it from the list, or browse them all.</div>
            <button
              onClick={() => setProjectScoped(false)}
              style={{
                padding: "var(--workspace-space-6) var(--workspace-space-16)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
                color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
              }}
            >
              Show all automations
            </button>
          </div>
        ) : automations.length === 0 ? (
          <div className="automation-empty">
            <h2>No automations yet</h2>
            <p>Choose when to run, which files to use, and where results should go.</p>
            <button type="button" onClick={() => setShowWizard(true)} className="automation-primary">Create an automation</button>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--workspace-muted)', fontSize: 'var(--workspace-font-control)' }}>
            No matching automations
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
            {filtered.map(auto => {
              const badge = TRIGGER_BADGES[auto.trigger_type] || TRIGGER_BADGES.folder_watch
              const isRunning = activeIds.has(auto.id)
              return (
                <div
                  key={auto.id}
                  onClick={() => openAutomation(auto.id)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: "var(--workspace-space-16) var(--workspace-space-16)",
                    backgroundColor: 'var(--workspace-surface)',
                    border: isRunning ? '1px solid rgba(234, 179, 8, 0.4)' : '1px solid var(--workspace-border)',
                    borderRadius: 'var(--workspace-radius-medium)',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'background-color 0.15s, border-color 0.15s',
                    animation: isRunning ? 'automationRowShimmer 2s ease-in-out infinite' : undefined,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.backgroundColor = 'var(--workspace-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'var(--workspace-surface)')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-6)' }}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        backgroundColor: isRunning ? '#eab308' : auto.enabled ? '#22c55e' : '#6b7280',
                        flexShrink: 0,
                        animation: isRunning ? 'automationPulseDot 1.5s ease-in-out infinite' : undefined,
                      }}
                    />
                    <button type="button" aria-label={`Open automation: ${auto.name}`} onClick={e => { e.stopPropagation(); openAutomation(auto.id) }} style={{ fontFamily: 'inherit', textAlign: 'left', background: 'transparent', border: 0, padding: 0, fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)', flex: 1, minWidth: 0, overflowWrap: 'anywhere', whiteSpace: 'normal', cursor: 'pointer' }}>
                      {auto.name}
                    </button>
                    {canPin && (() => {
                      const pinned = projectPins.isPinned('automation', auto.id)
                      return (
                        <button
                          type="button"
                          role="switch"
                          aria-checked={pinned}
                          aria-label={pinned ? 'Unpin from this project' : 'Pin to this project'}
                          onClick={(e) => togglePin(e, auto.id)}
                          title={pinned ? 'Unpin from this project' : 'Pin to this project'}
                          style={{
                            flexShrink: 0, display: 'flex', alignItems: 'center',
                            padding: 'var(--workspace-space-4)', background: 'transparent', border: 'none', cursor: 'pointer',
                            color: pinned ? 'var(--highlight-on-light)' : 'var(--workspace-muted)',
                          }}
                        >
                          {pinned ? <Pin size={13} fill="currentColor" /> : <PinOff size={13} />}
                        </button>
                      )
                    })()}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', marginBottom: 'var(--workspace-space-4)' }}>
                    <span
                      style={{
                        fontSize: 'var(--workspace-font-meta)',
                        fontWeight: 600,
                        padding: "var(--workspace-space-2) var(--workspace-space-8)",
                        borderRadius: 'var(--workspace-radius-large)',
                        color: 'var(--workspace-text)',
                        backgroundColor: 'var(--workspace-hover)',
                      }}
                    >
                      {badge.label}
                    </span>
                    <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{isRunning ? 'Running' : auto.enabled ? 'Enabled' : 'Disabled'}</span>
                    {auto.shared_with_team && (
                      <span style={{
                        fontSize: 'var(--workspace-font-meta)', fontWeight: 600, padding: "1px var(--workspace-space-6)", borderRadius: 'var(--workspace-radius-medium)',
                        color: '#0f5f5f', backgroundColor: '#e6f4f1',
                      }}>
                        Team
                      </span>
                    )}
                  </div>
                  <AutomationSummary automation={auto} names={folderNames} actionName={getActionName(auto)} compact />
                  <div style={{ marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: auto.last_event_status === 'failed' ? '#b91c1c' : 'var(--workspace-muted)' }}>
                    {auto.last_event_status ? `Last run: ${{ completed: 'Succeeded', failed: 'Failed', pending: 'Pending', queued: 'Queued', running: 'Running', skipped: 'Skipped' }[auto.last_event_status] || auto.last_event_status}${auto.last_event_at ? ` · ${formatRunTime(auto.last_event_at, String(auto.trigger_config?.timezone || 'UTC'))}` : ''}` : auto.last_event_status === null ? 'No runs yet' : 'Run history not reported'}
                  </div>
                  {auto.trigger_type === 'schedule'  && (auto.next_run_at || !auto.enabled) && !isRunning && (
                    <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', marginTop: 'var(--workspace-space-2)' }}>
                      {auto.enabled
                        ? `Next run ${formatRunTime(auto.next_run_at!, String(auto.trigger_config?.timezone || 'UTC'))}`
                        : 'Paused'}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <style>{`
        @keyframes automationPulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(1.4); }
        }
        @keyframes automationRowShimmer {
          0%, 100% { border-color: rgba(234, 179, 8, 0.2); }
          50% { border-color: rgba(234, 179, 8, 0.5); }
        }
      `}</style>

      {showWizard && (
        <AutomationCreationWizard
          onClose={() => setShowWizard(false)}
          onCreate={async id => {
            setShowWizard(false)
            // Created from inside a project: auto-pin so it shows in the
            // project's Automations tab (pins are the only project↔automation
            // link). Pin before refresh so the scoped list includes it.
            if (canPin) {
              try {
                await projectPins.pin('automation', id)
              } catch (err) {
                console.error('Failed to pin new automation to project:', err)
              }
            }
            refresh()
            openAutomation(id)
          }}
        />
      )}

      {showExplainer && <AutomationsExplainer onClose={() => setShowExplainer(false)} />}
    </div>
  )
}

// Small header chip that opens the feature explainer. Styled for the dark
// panel header so it reads as a secondary affordance next to the title.
export function ExplainerPill({ label, onClick, tone = 'dark' }: { label: string; onClick: () => void; tone?: 'light' | 'dark' }) {
  return (
    <button
      aria-label={label} title={label}
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
        padding: "var(--workspace-space-4) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
        color: tone === 'light' ? 'var(--workspace-muted)' : '#b5bbc3', backgroundColor: 'transparent',
        border: tone === 'light' ? '1px solid var(--workspace-border)' : '1px solid #3a3a3a', borderRadius: 999, cursor: 'pointer',
        transition: 'all 0.15s', whiteSpace: 'normal',
      }}
      onMouseEnter={e => { e.currentTarget.style.color = tone === 'light' ? '#202124' : '#ddd'; e.currentTarget.style.borderColor = '#555' }}
      onMouseLeave={e => { e.currentTarget.style.color = tone === 'light' ? '#59616b' : '#b5bbc3'; e.currentTarget.style.borderColor = '#3a3a3a' }}
    >
      <HelpCircle size={12} />
      About
    </button>
  )
}

function FilterPill({ label, count, active, onClick, icon }: {
  label: string
  count: number
  active: boolean
  onClick: () => void
  icon?: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      aria-label={`${label}: ${count} automations`}
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)',
        padding: "var(--workspace-space-4) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        fontFamily: 'inherit', borderRadius: 'var(--workspace-radius-large)',
        color: 'var(--workspace-text)',
        backgroundColor: active ? 'var(--workspace-selected)' : 'transparent',
        border: active ? '1px solid var(--highlight-on-light)' : '1px solid var(--workspace-border)',
        cursor: 'pointer', transition: 'all 0.12s',
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
      <span style={{
        fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        color: 'var(--workspace-muted)',
        marginLeft: 1,
      }}>
        {count}
      </span>
    </button>
  )
}
