import { useEffect, useMemo, useState } from 'react'
import { FolderSearch, Globe, Loader2, Mail, Plus, Search, X } from 'lucide-react'
import { AutomationsTutorial } from './AutomationsTutorial'
import { AutomationCreationWizard } from './AutomationCreationWizard'
import { useAutomations } from '../../hooks/useAutomations'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useSearchSets } from '../../hooks/useExtractions'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { getFeatureFlags } from '../../api/config'
import type { Automation, TriggerType } from '../../types/automation'

const TRIGGER_BADGES: Record<TriggerType, { label: string; color: string; bg: string }> = {
  folder_watch: { label: 'Folder Watch', color: '#1d4ed8', bg: '#dbeafe' },
  api: { label: 'API', color: '#7c3aed', bg: '#ede9fe' },
  m365_intake: { label: 'M365', color: '#15803d', bg: '#dcfce7' },
}

type FilterMode = 'all' | 'folder_watch' | 'api' | 'm365_intake'

export function AutomationsPanel({ activeIds = new Set<string>() }: { activeIds?: Set<string> }) {
  const { openAutomation, openAutomationId } = useWorkspace()
  const { automations, loading, refresh } = useAutomations()
  const { workflows } = useWorkflows()
  const { searchSets } = useSearchSets()

  const [filter, setFilter] = useState<FilterMode>('all')
  const [search, setSearch] = useState('')
  const [showWizard, setShowWizard] = useState(false)
  const [m365Enabled, setM365Enabled] = useState(false)

  useEffect(() => {
    getFeatureFlags().then(f => setM365Enabled(f.m365_enabled)).catch(() => {})
  }, [])

  // Refresh list when editor saves or closes
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
    m365_intake: automations.filter(a => a.trigger_type === 'm365_intake').length,
  }), [automations])

  const getActionName = (auto: Automation): string => {
    if (auto.action_type === 'workflow' && auto.action_id) {
      const name = auto.action_name || workflows.find(w => w.id === auto.action_id)?.name
      return name ? `Runs: ${name}` : 'Runs: (unknown workflow)'
    }
    if (auto.action_type === 'extraction' && auto.action_id) {
      const name = auto.action_name || searchSets.find(s => s.uuid === auto.action_id || s.id === auto.action_id)?.title
      return name ? `Extracts: ${name}` : 'Extracts: (unknown extraction)'
    }
    if (auto.action_type === 'task' && auto.action_id) {
      const name = auto.action_name || workflows.find(w => w.id === auto.action_id)?.name
      return name ? `Task: ${name}` : 'Task: (unknown workflow)'
    }
    if (auto.action_type === 'extraction') return 'No extraction selected'
    if (auto.action_type === 'task') return 'No task selected'
    return 'No action selected'
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e1e1e' }}>
      {/* Header */}
      <div
        style={{
          height: 50,
          backgroundColor: '#191919',
          boxShadow: '0 0px 23px -8px rgb(211, 211, 211)',
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          zIndex: 300,
          position: 'relative',
        }}
      >
        <span style={{ fontSize: 18, fontWeight: 600, color: '#fff' }}>Automations</span>
        <button
          onClick={() => setShowWizard(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 14px',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'inherit',
            color: 'var(--highlight-text-color, #000)',
            backgroundColor: 'var(--highlight-color, #eab308)',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          <Plus style={{ width: 14, height: 14 }} />
          New
        </button>
      </div>

      {/* Filter bar */}
      {automations.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 12px',
          backgroundColor: '#1e1e1e',
          borderBottom: '1px solid #2f2f2f',
          flexShrink: 0,
        }}>
          <FilterPill label="All" count={counts.all} active={filter === 'all'} onClick={() => setFilter('all')} />
          <FilterPill label="Folder Watch" count={counts.folder_watch} active={filter === 'folder_watch'} onClick={() => setFilter('folder_watch')} icon={<FolderSearch size={10} />} />
          <FilterPill label="API" count={counts.api} active={filter === 'api'} onClick={() => setFilter('api')} icon={<Globe size={10} />} />
          {m365Enabled && <FilterPill label="M365" count={counts.m365_intake} active={filter === 'm365_intake'} onClick={() => setFilter('m365_intake')} icon={<Mail size={10} />} />}
          <div style={{ flex: 1 }} />
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '0 8px', height: 26,
            backgroundColor: '#191919', border: '1px solid #3a3a3a', borderRadius: 5,
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
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : automations.length === 0 ? (
          <AutomationsTutorial />
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#666', fontSize: 13 }}>
            No matching automations
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {filtered.map(auto => {
              const badge = TRIGGER_BADGES[auto.trigger_type] || TRIGGER_BADGES.folder_watch
              const isRunning = activeIds.has(auto.id)
              return (
                <button
                  key={auto.id}
                  onClick={() => openAutomation(auto.id)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '14px 16px',
                    backgroundColor: '#2a2a2a',
                    border: isRunning ? '1px solid rgba(234, 179, 8, 0.4)' : '1px solid #3a3a3a',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'background-color 0.15s, border-color 0.15s',
                    animation: isRunning ? 'automationRowShimmer 2s ease-in-out infinite' : undefined,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#333')}
                  onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
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
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {auto.name}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: 10,
                        color: badge.color,
                        backgroundColor: badge.bg,
                      }}
                    >
                      {badge.label}
                    </span>
                    {auto.shared_with_team && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                        color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
                      }}>
                        Team
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: isRunning ? '#eab308' : '#999', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {isRunning ? 'Running...' : getActionName(auto)}
                  </div>
                </button>
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
          onCreate={id => {
            setShowWizard(false)
            refresh()
            openAutomation(id)
          }}
        />
      )}
    </div>
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
