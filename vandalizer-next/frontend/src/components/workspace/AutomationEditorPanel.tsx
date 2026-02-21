import { useCallback, useEffect, useRef, useState } from 'react'
import { X, Pencil, Trash2, FolderOpen, Globe, Clock, Zap } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { getAutomation, updateAutomation, deleteAutomation } from '../../api/automations'
import { useWorkflows } from '../../hooks/useWorkflows'
import type { Automation, TriggerType, ActionType } from '../../types/automation'

const TRIGGER_OPTIONS: { value: TriggerType; label: string; icon: typeof FolderOpen; description: string }[] = [
  { value: 'folder_watch', label: 'Folder Watch', icon: FolderOpen, description: 'Trigger when files are added to a folder' },
  { value: 'api', label: 'API Endpoint', icon: Globe, description: 'Trigger via HTTP POST request' },
  { value: 'schedule', label: 'Schedule', icon: Clock, description: 'Trigger on a recurring schedule' },
]

const ACTION_OPTIONS: { value: ActionType; label: string; description: string; enabled: boolean }[] = [
  { value: 'workflow', label: 'Run Workflow', description: 'Execute a workflow on triggered documents', enabled: true },
  { value: 'extraction', label: 'Run Extraction', description: 'Run an extraction template', enabled: false },
  { value: 'task', label: 'Run Task', description: 'Execute a standalone task', enabled: false },
]

export function AutomationEditorPanel() {
  const { openAutomationId, closeAutomation } = useWorkspace()
  const { workflows } = useWorkflows()
  const [automation, setAutomation] = useState<Automation | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const titleInputRef = useRef<HTMLInputElement>(null)
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refresh = useCallback(async () => {
    if (!openAutomationId) return
    setLoading(true)
    try {
      const auto = await getAutomation(openAutomationId)
      setAutomation(auto)
    } finally {
      setLoading(false)
    }
  }, [openAutomationId])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (editingTitle && titleInputRef.current) {
      titleInputRef.current.focus()
      titleInputRef.current.select()
    }
  }, [editingTitle])

  const save = useCallback(async (updates: Parameters<typeof updateAutomation>[1]) => {
    if (!openAutomationId) return
    const updated = await updateAutomation(openAutomationId, updates)
    setAutomation(updated)
  }, [openAutomationId])

  const debouncedSave = useCallback((updates: Parameters<typeof updateAutomation>[1]) => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current)
    saveTimeoutRef.current = setTimeout(() => save(updates), 500)
  }, [save])

  useEffect(() => {
    return () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current) }
  }, [])

  const handleTitleSave = async () => {
    if (!titleValue.trim()) {
      setEditingTitle(false)
      return
    }
    await save({ name: titleValue.trim() })
    setEditingTitle(false)
  }

  const handleDelete = async () => {
    if (!openAutomationId) return
    await deleteAutomation(openAutomationId)
    closeAutomation()
  }

  const handleToggleEnabled = async () => {
    if (!automation) return
    await save({ enabled: !automation.enabled })
  }

  const handleTriggerTypeChange = async (type: TriggerType) => {
    await save({ trigger_type: type, trigger_config: {} })
  }

  const handleActionTypeChange = async (type: ActionType) => {
    await save({ action_type: type, action_id: null })
  }

  const handleWorkflowSelect = async (workflowId: string) => {
    await save({ action_id: workflowId || null })
  }

  if (loading) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <EditorHeader title="Loading..." onClose={closeAutomation} />
        <div style={{ padding: 40, textAlign: 'center', color: '#888', fontSize: 13 }}>Loading automation...</div>
      </div>
    )
  }

  if (!automation) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <EditorHeader title="Automation" onClose={closeAutomation} />
        <div style={{ padding: 40, textAlign: 'center', color: '#d93025', fontSize: 13 }}>Automation not found.</div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
      {/* Header */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {editingTitle ? (
            <input
              ref={titleInputRef}
              value={titleValue}
              onChange={e => setTitleValue(e.target.value)}
              onBlur={handleTitleSave}
              onKeyDown={e => {
                if (e.key === 'Enter') handleTitleSave()
                if (e.key === 'Escape') setEditingTitle(false)
              }}
              style={{
                fontSize: 18, fontWeight: 600, color: '#202124', border: '1px solid #d1d5db',
                borderRadius: 4, padding: '2px 8px', fontFamily: 'inherit', outline: 'none',
                flex: 1, marginRight: 8,
              }}
            />
          ) : (
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', flex: 1 }}
              onClick={() => { setTitleValue(automation.name); setEditingTitle(true) }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, color: '#202124', letterSpacing: '-0.01em' }}>
                {automation.name}
              </span>
              <Pencil style={{ width: 14, height: 14, color: '#9ca3af' }} />
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {/* Enabled toggle */}
            <button
              onClick={handleToggleEnabled}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px',
                fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                color: automation.enabled ? '#15803d' : '#6b7280',
                backgroundColor: automation.enabled ? '#dcfce7' : '#f3f4f6',
                border: '1px solid ' + (automation.enabled ? '#bbf7d0' : '#e5e7eb'),
                borderRadius: 16, cursor: 'pointer',
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                backgroundColor: automation.enabled ? '#22c55e' : '#9ca3af',
              }} />
              {automation.enabled ? 'Enabled' : 'Disabled'}
            </button>
            {/* Delete */}
            <button
              onClick={handleDelete}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#d93025', display: 'flex' }}
              title="Delete automation"
            >
              <Trash2 style={{ width: 16, height: 16 }} />
            </button>
            {/* Close */}
            <button
              onClick={closeAutomation}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#5f6368', display: 'flex' }}
            >
              <X style={{ width: 20, height: 20 }} />
            </button>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px', minHeight: 0 }}>
        {/* Section A — Trigger */}
        <SectionLabel>Trigger</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 32 }}>
          {TRIGGER_OPTIONS.map(opt => {
            const Icon = opt.icon
            const selected = automation.trigger_type === opt.value
            return (
              <button
                key={opt.value}
                onClick={() => handleTriggerTypeChange(opt.value)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 16px',
                  backgroundColor: selected ? '#eff6ff' : '#fff',
                  border: selected ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                  borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                  textAlign: 'left', width: '100%',
                }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: 8,
                  backgroundColor: selected ? '#dbeafe' : '#f3f4f6',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <Icon style={{ width: 18, height: 18, color: selected ? '#2563eb' : '#6b7280' }} />
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{opt.label}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.description}</div>
                </div>
              </button>
            )
          })}
        </div>

        {/* Trigger config card */}
        <TriggerConfigCard
          automation={automation}
          onSave={debouncedSave}
        />

        {/* Section B — Action */}
        <SectionLabel>Action</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {ACTION_OPTIONS.map(opt => {
            const selected = automation.action_type === opt.value
            return (
              <button
                key={opt.value}
                onClick={() => opt.enabled && handleActionTypeChange(opt.value)}
                disabled={!opt.enabled}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 16px',
                  backgroundColor: selected && opt.enabled ? '#eff6ff' : '#fff',
                  border: selected && opt.enabled ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                  borderRadius: 8, fontFamily: 'inherit',
                  textAlign: 'left', width: '100%',
                  cursor: opt.enabled ? 'pointer' : 'default',
                  opacity: opt.enabled ? 1 : 0.5,
                  position: 'relative',
                }}
              >
                <div style={{
                  width: 18, height: 18, borderRadius: '50%',
                  border: selected && opt.enabled ? '5px solid #3b82f6' : '2px solid #d1d5db',
                  backgroundColor: '#fff', flexShrink: 0,
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{opt.label}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.description}</div>
                </div>
                {!opt.enabled && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
                    backgroundColor: '#f3f4f6', color: '#9ca3af', textTransform: 'uppercase',
                  }}>
                    Coming Soon
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Workflow selector */}
        {automation.action_type === 'workflow' && (
          <div style={{ marginTop: 16, padding: '16px', backgroundColor: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' }}>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 8 }}>
              Select Workflow
            </label>
            <select
              value={automation.action_id || ''}
              onChange={e => handleWorkflowSelect(e.target.value)}
              style={{
                width: '100%', padding: '8px 12px', fontSize: 13,
                border: '1px solid #d1d5db', borderRadius: 6, fontFamily: 'inherit',
                backgroundColor: '#fff', color: '#202124', outline: 'none',
              }}
            >
              <option value="">-- Select a workflow --</option>
              {workflows.map(wf => (
                <option key={wf.id} value={wf.id}>{wf.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>
    </div>
  )
}

function EditorHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '16px 24px', borderBottom: '1px solid #e5e7eb', backgroundColor: '#fff', flexShrink: 0,
    }}>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#202124', letterSpacing: '-0.01em' }}>{title}</div>
      <button
        onClick={onClose}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#5f6368', display: 'flex' }}
      >
        <X style={{ width: 20, height: 20 }} />
      </button>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 13, fontWeight: 700, color: '#374151', textTransform: 'uppercase',
      letterSpacing: '0.05em', marginBottom: 12,
    }}>
      {children}
    </div>
  )
}

function TriggerConfigCard({ automation, onSave }: { automation: Automation; onSave: (updates: Record<string, unknown>) => void }) {
  if (automation.trigger_type === 'folder_watch') {
    return <FolderWatchConfig automation={automation} onSave={onSave} />
  }
  if (automation.trigger_type === 'api') {
    return <ApiConfig automation={automation} />
  }
  if (automation.trigger_type === 'schedule') {
    return (
      <div style={{
        padding: '20px', marginBottom: 32, backgroundColor: '#f9fafb', borderRadius: 8,
        border: '1px solid #e5e7eb', textAlign: 'center', color: '#9ca3af', fontSize: 13,
      }}>
        Schedule configuration coming soon
      </div>
    )
  }
  return null
}

function FolderWatchConfig({ automation, onSave }: { automation: Automation; onSave: (updates: Record<string, unknown>) => void }) {
  const config = (automation.trigger_config || {}) as Record<string, unknown>
  const fileTypes = (config.file_types as string[] | undefined) || ['pdf', 'docx', 'xlsx', 'html']
  const excludePatterns = (config.exclude_patterns as string | undefined) || ''
  const batchMode = (config.batch_mode as boolean | undefined) || false

  const FILE_TYPE_OPTIONS = ['pdf', 'docx', 'xlsx', 'html', 'txt', 'csv']

  const handleFileTypeToggle = (type: string) => {
    const next = fileTypes.includes(type)
      ? fileTypes.filter(t => t !== type)
      : [...fileTypes, type]
    onSave({ trigger_config: { ...config, file_types: next } })
  }

  return (
    <div style={{ padding: '16px', marginBottom: 32, backgroundColor: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 8 }}>
        File Types
      </label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {FILE_TYPE_OPTIONS.map(type => (
          <button
            key={type}
            onClick={() => handleFileTypeToggle(type)}
            style={{
              padding: '4px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 14, cursor: 'pointer',
              backgroundColor: fileTypes.includes(type) ? '#dbeafe' : '#f3f4f6',
              color: fileTypes.includes(type) ? '#1d4ed8' : '#6b7280',
              border: fileTypes.includes(type) ? '1px solid #93c5fd' : '1px solid #e5e7eb',
            }}
          >
            .{type}
          </button>
        ))}
      </div>

      <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 8 }}>
        Exclude Patterns
      </label>
      <input
        type="text"
        placeholder="e.g. draft*, temp_*"
        defaultValue={excludePatterns}
        onBlur={e => onSave({ trigger_config: { ...config, exclude_patterns: e.target.value } })}
        style={{
          width: '100%', padding: '8px 12px', fontSize: 13, border: '1px solid #d1d5db',
          borderRadius: 6, fontFamily: 'inherit', outline: 'none', marginBottom: 16,
          boxSizing: 'border-box',
        }}
      />

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
        <input
          type="checkbox"
          checked={batchMode}
          onChange={e => onSave({ trigger_config: { ...config, batch_mode: e.target.checked } })}
          style={{ width: 16, height: 16, accentColor: '#3b82f6' }}
        />
        <span style={{ fontWeight: 500 }}>Batch mode</span>
        <span style={{ color: '#9ca3af', fontSize: 12 }}>— wait and process files together</span>
      </label>
    </div>
  )
}

function ApiConfig({ automation }: { automation: Automation }) {
  const endpoint = `POST /api/automations/${automation.id}/trigger`

  return (
    <div style={{ padding: '16px', marginBottom: 32, backgroundColor: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 8 }}>
        Trigger Endpoint
      </label>
      <div style={{
        padding: '10px 14px', backgroundColor: '#1e1e1e', borderRadius: 6, fontFamily: 'monospace',
        fontSize: 13, color: '#e5e5e5', userSelect: 'all',
      }}>
        {endpoint}
      </div>
      <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 8 }}>
        Send a POST request to this endpoint to trigger the automation.
      </div>
    </div>
  )
}
