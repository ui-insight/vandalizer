import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, FolderSearch, Globe, Loader2, Plus, Search, X, Zap } from 'lucide-react'
import { useAutomations } from '../../hooks/useAutomations'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useSearchSets } from '../../hooks/useExtractions'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { AutomationCreationWizard } from '../workspace/AutomationCreationWizard'
import type { Automation, TriggerType } from '../../types/automation'

type FilterMode = 'all' | 'folder_watch' | 'api'

const TRIGGER_BADGES: Record<TriggerType, { label: string; color: string; bg: string }> = {
  folder_watch: { label: 'Folder Watch', color: '#1d4ed8', bg: '#dbeafe' },
  api: { label: 'API', color: '#7c3aed', bg: '#ede9fe' },
  m365_intake: { label: 'M365', color: '#15803d', bg: '#dcfce7' },
}

export function KBAutomationsBar({ activeIds = new Set<string>() }: { activeIds?: Set<string> }) {
  const { openAutomation, openAutomationId } = useWorkspace()
  const { automations, loading, refresh } = useAutomations()
  const { workflows } = useWorkflows()
  const { searchSets } = useSearchSets()

  const [expanded, setExpanded] = useState(true)
  const [filter, setFilter] = useState<FilterMode>('all')
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)

  // Refresh when editor closes
  useEffect(() => {
    if (openAutomationId === null) refresh()
    const handler = () => refresh()
    window.addEventListener('automations-updated', handler)
    return () => window.removeEventListener('automations-updated', handler)
  }, [openAutomationId])

  const filtered = useMemo(() => {
    let list = automations
    if (filter !== 'all') list = list.filter(a => a.trigger_type === filter)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) ||
        (a.description || '').toLowerCase().includes(q),
      )
    }
    return list
  }, [automations, filter, search])

  const counts = useMemo(() => ({
    all: automations.length,
    folder_watch: automations.filter(a => a.trigger_type === 'folder_watch').length,
    api: automations.filter(a => a.trigger_type === 'api').length,
  }), [automations])

  const getActionName = (auto: Automation): string => {
    if (auto.action_type === 'workflow' && auto.action_id) {
      const wf = workflows.find(w => w.id === auto.action_id)
      return wf ? wf.name : '(unknown workflow)'
    }
    if (auto.action_type === 'extraction' && auto.action_id) {
      const ss = searchSets.find(s => s.uuid === auto.action_id)
      return ss ? ss.title : '(unknown extraction)'
    }
    if (auto.action_type === 'task' && auto.action_id) {
      const wf = workflows.find(w => w.id === auto.action_id)
      return wf ? wf.name : '(unknown workflow)'
    }
    return 'No action'
  }

  const activeCount = automations.filter(a => activeIds.has(a.id)).length

  return (
    <>
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          padding: '10px 16px', fontSize: 12, fontWeight: 700,
          fontFamily: 'inherit', textTransform: 'uppercase', letterSpacing: 0.5,
          color: '#999', backgroundColor: '#242424',
          border: 'none', borderBottom: '1px solid #2f2f2f',
          cursor: 'pointer', transition: 'background-color 0.15s',
        }}
        onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
        onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#242424')}
      >
        {expanded
          ? <ChevronDown size={13} style={{ color: '#666' }} />
          : <ChevronRight size={13} style={{ color: '#666' }} />}
        <Zap size={12} style={{ color: 'var(--highlight-color, #eab308)' }} />
        <span>Automations</span>
        {!expanded && counts.all > 0 && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 7px', borderRadius: 10,
            color: '#aaa', backgroundColor: '#333', marginLeft: 2,
          }}>
            {counts.all}
          </span>
        )}
        {!expanded && activeCount > 0 && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 7px', borderRadius: 10,
            color: '#eab308', backgroundColor: 'rgba(234, 179, 8, 0.15)',
            animation: 'automationPulseDot 1.5s ease-in-out infinite',
          }}>
            {activeCount} running
          </span>
        )}
        <div style={{ flex: 1 }} />
        <span
          onClick={e => { e.stopPropagation(); setShowWizard(true) }}
          title="New automation"
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 20, height: 20, borderRadius: 4,
            color: 'var(--highlight-text-color, #000)',
            backgroundColor: 'var(--highlight-color, #eab308)',
            fontSize: 13, fontWeight: 700, lineHeight: 1,
          }}
        >
          <Plus size={12} />
        </span>
      </button>

      {expanded && (
        <div style={{ backgroundColor: '#242424', borderBottom: '1px solid #2f2f2f' }}>
          {/* Filter toggles + search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px' }}>
            {/* Filter pills */}
            <FilterPill
              label="All"
              count={counts.all}
              active={filter === 'all'}
              onClick={() => setFilter('all')}
            />
            <FilterPill
              label="Folder Watch"
              count={counts.folder_watch}
              active={filter === 'folder_watch'}
              onClick={() => setFilter('folder_watch')}
              icon={<FolderSearch size={10} />}
            />
            <FilterPill
              label="API"
              count={counts.api}
              active={filter === 'api'}
              onClick={() => setFilter('api')}
              icon={<Globe size={10} />}
            />

            <div style={{ flex: 1 }} />

            {/* Inline search */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '0 8px', height: 26,
              backgroundColor: '#1e1e1e', border: '1px solid #3a3a3a', borderRadius: 5,
              maxWidth: 160,
            }}>
              <Search size={11} style={{ color: '#555', flexShrink: 0 }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Filter..."
                style={{
                  flex: 1, width: 60, padding: 0, fontSize: 11, fontFamily: 'inherit',
                  color: '#ccc', backgroundColor: 'transparent',
                  border: 'none', outline: 'none',
                }}
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}
                >
                  <X size={10} style={{ color: '#555' }} />
                </button>
              )}
            </div>
          </div>

          {/* Automation cards */}
          <div style={{
            padding: '0 12px 10px', display: 'flex', flexDirection: 'column', gap: 4,
            maxHeight: 220, overflowY: 'auto',
          }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 16, color: '#666' }}>
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '12px 0', fontSize: 12, color: '#555' }}>
                {automations.length === 0
                  ? 'No automations yet'
                  : 'No matching automations'}
              </div>
            ) : (
              filtered.map(auto => {
                const badge = TRIGGER_BADGES[auto.trigger_type] || TRIGGER_BADGES.folder_watch
                const isRunning = activeIds.has(auto.id)
                return (
                  <button
                    key={auto.id}
                    onClick={() => openAutomation(auto.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      width: '100%', textAlign: 'left',
                      padding: '8px 12px',
                      backgroundColor: '#2a2a2a',
                      border: isRunning ? '1px solid rgba(234, 179, 8, 0.35)' : '1px solid #333',
                      borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                      transition: 'background-color 0.12s, border-color 0.12s',
                      animation: isRunning ? 'automationRowShimmer 2s ease-in-out infinite' : undefined,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#333')}
                    onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
                  >
                    {/* Status dot */}
                    <span style={{
                      width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                      backgroundColor: isRunning ? '#eab308' : auto.enabled ? '#22c55e' : '#555',
                      animation: isRunning ? 'automationPulseDot 1.5s ease-in-out infinite' : undefined,
                    }} />

                    {/* Name + action */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 600, color: '#e5e5e5',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {auto.name}
                      </div>
                      <div style={{
                        fontSize: 11, color: isRunning ? '#eab308' : '#777',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {isRunning ? 'Running...' : getActionName(auto)}
                      </div>
                    </div>

                    {/* Badges */}
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 10,
                      color: badge.color, backgroundColor: badge.bg, flexShrink: 0,
                      whiteSpace: 'nowrap',
                    }}>
                      {badge.label}
                    </span>
                    {auto.shared_with_team && (
                      <span style={{
                        fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 8,
                        color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
                        flexShrink: 0,
                      }}>
                        Team
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}

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
          onCreate={id => {
            setShowWizard(false)
            refresh()
            openAutomation(id)
          }}
        />
      )}
    </>
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
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '3px 10px', fontSize: 11, fontWeight: 600,
        fontFamily: 'inherit', borderRadius: 12,
        color: active ? '#fff' : '#888',
        backgroundColor: active ? '#3a3a3a' : 'transparent',
        border: active ? '1px solid #555' : '1px solid transparent',
        cursor: 'pointer', transition: 'all 0.12s',
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
      <span style={{
        fontSize: 10, fontWeight: 600,
        color: active ? '#ccc' : '#555',
        marginLeft: 1,
      }}>
        {count}
      </span>
    </button>
  )
}
