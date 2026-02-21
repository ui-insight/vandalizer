import { useState } from 'react'
import { Plus, Loader2, Zap } from 'lucide-react'
import { useAutomations } from '../../hooks/useAutomations'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import type { Automation, TriggerType } from '../../types/automation'

const TRIGGER_BADGES: Record<TriggerType, { label: string; color: string; bg: string }> = {
  folder_watch: { label: 'Folder Watch', color: '#1d4ed8', bg: '#dbeafe' },
  api: { label: 'API', color: '#7c3aed', bg: '#ede9fe' },
  schedule: { label: 'Schedule', color: '#c2410c', bg: '#ffedd5' },
  m365_intake: { label: 'M365', color: '#15803d', bg: '#dcfce7' },
}

export function AutomationsPanel() {
  const { openAutomation } = useWorkspace()
  const { automations, loading, create } = useAutomations()
  const { workflows } = useWorkflows()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const auto = await create('New Automation')
      openAutomation(auto.id)
    } catch (err) {
      console.error('Failed to create automation:', err)
      setError(err instanceof Error ? err.message : 'Failed to create automation')
    } finally {
      setCreating(false)
    }
  }

  const getActionName = (auto: Automation): string => {
    if (auto.action_type === 'workflow' && auto.action_id) {
      const wf = workflows.find(w => w.id === auto.action_id)
      return wf ? `Runs: ${wf.name}` : 'Runs: (unknown workflow)'
    }
    if (auto.action_type === 'extraction') return 'Extraction (coming soon)'
    if (auto.action_type === 'task') return 'Task (coming soon)'
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
          onClick={handleCreate}
          disabled={creating}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 14px',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'inherit',
            color: '#000',
            backgroundColor: 'var(--highlight-color, #eab308)',
            border: 'none',
            borderRadius: 6,
            cursor: creating ? 'default' : 'pointer',
            opacity: creating ? 0.6 : 1,
          }}
        >
          {creating ? <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> : <Plus style={{ width: 14, height: 14 }} />}
          New
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          margin: '8px 12px 0', padding: '8px 12px', fontSize: 12,
          color: '#b91c1c', backgroundColor: '#fef2f2', borderRadius: 6,
          border: '1px solid #fecaca',
        }}>
          {error}
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : automations.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#888' }}>
            <Zap style={{ width: 32, height: 32, margin: '0 auto 12px', opacity: 0.4 }} />
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>No automations yet</div>
            <div style={{ fontSize: 12 }}>Click "+ New" to create your first automation</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {automations.map(auto => {
              const badge = TRIGGER_BADGES[auto.trigger_type] || TRIGGER_BADGES.folder_watch
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
                    border: '1px solid #3a3a3a',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'background-color 0.15s',
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
                        backgroundColor: auto.enabled ? '#22c55e' : '#6b7280',
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {auto.name}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
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
                  </div>
                  <div style={{ fontSize: 12, color: '#999', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {getActionName(auto)}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
