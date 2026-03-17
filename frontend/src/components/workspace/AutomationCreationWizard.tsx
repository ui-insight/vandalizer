import { useEffect, useRef, useState } from 'react'
import { X, FolderOpen, Globe, Loader2 } from 'lucide-react'
import { createAutomation } from '../../api/automations'
import { apiFetch } from '../../api/client'
import type { ActionType, TriggerType } from '../../types/automation'
import type { Workflow } from '../../types/workflow'

interface SearchSet { uuid: string; title: string }

interface Props {
  onClose: () => void
  onCreate: (id: string) => void
  workflows: Workflow[]
  searchSets: SearchSet[]
}

const TRIGGER_OPTIONS: { value: TriggerType; label: string; icon: typeof FolderOpen; description: string }[] = [
  { value: 'folder_watch', label: 'Folder Watch', icon: FolderOpen, description: 'Trigger when files are added to a folder' },
  { value: 'api', label: 'API Endpoint', icon: Globe, description: 'Trigger via HTTP POST request' },
]

const ACTION_OPTIONS: { value: ActionType; label: string; description: string }[] = [
  { value: 'workflow', label: 'Run Workflow', description: 'Execute a workflow on triggered documents' },
  { value: 'extraction', label: 'Run Extraction', description: 'Run an extraction template' },
  { value: 'task', label: 'Run Task', description: 'Execute a standalone task' },
]

const FILE_TYPE_OPTIONS = ['pdf', 'docx', 'xlsx', 'html', 'txt', 'csv']

export function AutomationCreationWizard({ onClose, onCreate, workflows, searchSets }: Props) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [triggerType, setTriggerType] = useState<TriggerType>('folder_watch')
  const [actionType, setActionType] = useState<ActionType>('workflow')
  const [actionId, setActionId] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  // Folder watch config state
  const [folders, setFolders] = useState<{ uuid: string; path: string }[]>([])
  const [foldersLoading, setFoldersLoading] = useState(false)
  const [watchFolderId, setWatchFolderId] = useState('')
  const [fileTypes, setFileTypes] = useState<string[]>(['pdf', 'docx', 'xlsx', 'html'])
  const [excludePatterns, setExcludePatterns] = useState('')
  const [batchMode, setBatchMode] = useState(false)

  // Dynamic step count: folder_watch adds a config step
  const hasFolderStep = triggerType === 'folder_watch'
  const totalSteps = hasFolderStep ? 4 : 3

  // Map logical step to content:
  // folder_watch: 1=name, 2=trigger, 3=folder config, 4=action
  // api:          1=name, 2=trigger, 3=action
  const actionStep = hasFolderStep ? 4 : 3
  const folderStep = 3 // only used when hasFolderStep

  useEffect(() => {
    if (step === 1) nameRef.current?.focus()
  }, [step])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Load folders when entering the folder config step
  useEffect(() => {
    if (hasFolderStep && step === folderStep && folders.length === 0) {
      setFoldersLoading(true)
      apiFetch<{ uuid: string; path: string }[]>('/api/folders/all')
        .then(setFolders)
        .catch(() => {})
        .finally(() => setFoldersLoading(false))
    }
  }, [step, hasFolderStep, folderStep, folders.length])

  const canAdvance = (): boolean => {
    if (step === 1) return name.trim().length > 0
    if (step === 2) return true
    if (hasFolderStep && step === folderStep) return watchFolderId.length > 0
    if (step === actionStep) return actionId.length > 0
    return false
  }

  const handleActionTypeChange = (type: ActionType) => {
    setActionType(type)
    setActionId('')
  }

  // When trigger type changes away from folder_watch, reset folder config and
  // clamp step if we're on the folder step that no longer exists
  const handleTriggerTypeChange = (type: TriggerType) => {
    setTriggerType(type)
    if (type !== 'folder_watch') {
      setWatchFolderId('')
      setFileTypes(['pdf', 'docx', 'xlsx', 'html'])
      setExcludePatterns('')
      setBatchMode(false)
    }
  }

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const triggerConfig = triggerType === 'folder_watch'
        ? {
            folder_id: watchFolderId || undefined,
            file_types: fileTypes,
            exclude_patterns: excludePatterns || undefined,
            batch_mode: batchMode,
          }
        : undefined

      const auto = await createAutomation({
        name: name.trim(),
        description: description.trim() || undefined,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        action_type: actionType,
        action_id: actionId || undefined,
      })
      onCreate(auto.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create automation')
      setCreating(false)
    }
  }

  const handleFileTypeToggle = (type: string) => {
    setFileTypes(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    )
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '10px 14px', fontSize: 14, fontFamily: 'inherit',
    border: '1px solid #d1d5db', borderRadius: 8, outline: 'none',
    boxSizing: 'border-box', color: '#202124', transition: 'border-color 0.15s',
  }

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    backgroundColor: '#fff', cursor: 'pointer',
  }

  const btnPrimary = (enabled: boolean): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '9px 20px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
    border: 'none', borderRadius: 8,
    cursor: enabled ? 'pointer' : 'not-allowed',
    backgroundColor: enabled ? '#191919' : '#e5e7eb',
    color: enabled ? '#fff' : '#9ca3af',
    transition: 'background-color 0.15s',
  })

  const btnSecondary: React.CSSProperties = {
    padding: '9px 20px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
    border: '1px solid #d1d5db', borderRadius: 8, cursor: 'pointer',
    backgroundColor: '#fff', color: '#374151',
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 2000,
        backgroundColor: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        backgroundColor: '#fff', borderRadius: 14, width: 540, maxWidth: '92vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.18)',
        display: 'flex', flexDirection: 'column', maxHeight: '90vh',
        overflow: 'hidden',
      }}>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px 0',
        }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: '#111', letterSpacing: '-0.01em' }}>
              New Automation
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
              Step {step} of {totalSteps}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 6, color: '#9ca3af', display: 'flex' }}
          >
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>

        {/* Progress bar */}
        <div style={{ height: 3, backgroundColor: '#f3f4f6', margin: '16px 0 0' }}>
          <div style={{
            height: '100%',
            width: `${(step / totalSteps) * 100}%`,
            backgroundColor: '#3b82f6',
            borderRadius: '0 2px 2px 0',
            transition: 'width 0.25s ease',
          }} />
        </div>

        {/* Body */}
        <div style={{ padding: '28px 28px 20px', flex: 1, overflowY: 'auto' }}>

          {/* Step 1: Name */}
          {step === 1 && (
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#202124', marginBottom: 20 }}>
                What would you like to call this automation?
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Name <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  ref={nameRef}
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && canAdvance()) setStep(2) }}
                  placeholder="e.g. Process grant applications"
                  style={inputStyle}
                  onFocus={e => (e.currentTarget.style.borderColor = '#3b82f6')}
                  onBlur={e => (e.currentTarget.style.borderColor = '#d1d5db')}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Description <span style={{ color: '#9ca3af', fontWeight: 400 }}>(optional)</span>
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="What does this automation do?"
                  style={inputStyle}
                  onFocus={e => (e.currentTarget.style.borderColor = '#3b82f6')}
                  onBlur={e => (e.currentTarget.style.borderColor = '#d1d5db')}
                />
              </div>
            </div>
          )}

          {/* Step 2: Trigger */}
          {step === 2 && (
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#202124', marginBottom: 20 }}>
                What will trigger this automation?
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {TRIGGER_OPTIONS.map(opt => {
                  const Icon = opt.icon
                  const selected = triggerType === opt.value
                  return (
                    <button
                      key={opt.value}
                      onClick={() => handleTriggerTypeChange(opt.value)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 14,
                        padding: '14px 16px',
                        backgroundColor: selected ? '#eff6ff' : '#fff',
                        border: selected ? '2px solid #3b82f6' : '1.5px solid #e5e7eb',
                        borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit',
                        textAlign: 'left', width: '100%', transition: 'border-color 0.1s, background-color 0.1s',
                      }}
                    >
                      <div style={{
                        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                        backgroundColor: selected ? '#dbeafe' : '#f3f4f6',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'background-color 0.1s',
                      }}>
                        <Icon style={{ width: 18, height: 18, color: selected ? '#2563eb' : '#6b7280' }} />
                      </div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{opt.label}</div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{opt.description}</div>
                      </div>
                      <div style={{ marginLeft: 'auto' }}>
                        <div style={{
                          width: 18, height: 18, borderRadius: '50%',
                          border: selected ? '5px solid #3b82f6' : '2px solid #d1d5db',
                          backgroundColor: '#fff', flexShrink: 0, transition: 'border 0.1s',
                        }} />
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Step 3 (folder_watch only): Folder Config */}
          {hasFolderStep && step === folderStep && (
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#202124', marginBottom: 20 }}>
                Configure folder watch
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Watch Folder <span style={{ color: '#ef4444' }}>*</span>
                </label>
                {foldersLoading ? (
                  <div style={{ padding: '10px 14px', fontSize: 13, color: '#9ca3af' }}>Loading folders...</div>
                ) : (
                  <select
                    value={watchFolderId}
                    onChange={e => setWatchFolderId(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="">-- Select a folder to watch --</option>
                    {folders.map(f => (
                      <option key={f.uuid} value={f.uuid}>{f.path}</option>
                    ))}
                  </select>
                )}
                {!foldersLoading && folders.length === 0 && (
                  <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>No folders yet — create one in the workspace first.</div>
                )}
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  File Types
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
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
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Exclude Patterns <span style={{ color: '#9ca3af', fontWeight: 400 }}>(optional)</span>
                </label>
                <input
                  type="text"
                  value={excludePatterns}
                  onChange={e => setExcludePatterns(e.target.value)}
                  placeholder="e.g. draft*, temp_*"
                  style={inputStyle}
                  onFocus={e => (e.currentTarget.style.borderColor = '#3b82f6')}
                  onBlur={e => (e.currentTarget.style.borderColor = '#d1d5db')}
                />
              </div>

              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
                <input
                  type="checkbox"
                  checked={batchMode}
                  onChange={e => setBatchMode(e.target.checked)}
                  style={{ width: 16, height: 16, accentColor: '#3b82f6' }}
                />
                <span style={{ fontWeight: 500 }}>Batch mode</span>
                <span style={{ color: '#9ca3af', fontSize: 12 }}>&mdash; wait and process files together</span>
              </label>
            </div>
          )}

          {/* Action step (step 3 for API, step 4 for folder_watch) */}
          {step === actionStep && (
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#202124', marginBottom: 20 }}>
                What should happen when it triggers?
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                {ACTION_OPTIONS.map(opt => {
                  const selected = actionType === opt.value
                  return (
                    <button
                      key={opt.value}
                      onClick={() => handleActionTypeChange(opt.value)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '12px 16px',
                        backgroundColor: selected ? '#eff6ff' : '#fff',
                        border: selected ? '2px solid #3b82f6' : '1.5px solid #e5e7eb',
                        borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                        textAlign: 'left', width: '100%', transition: 'border-color 0.1s',
                      }}
                    >
                      <div style={{
                        width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                        border: selected ? '5px solid #3b82f6' : '2px solid #d1d5db',
                        backgroundColor: '#fff', transition: 'border 0.1s',
                      }} />
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{opt.label}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.description}</div>
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Action selector */}
              {actionType === 'workflow' && (
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Select Workflow <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <select value={actionId} onChange={e => setActionId(e.target.value)} style={selectStyle}>
                    <option value="">— choose a workflow —</option>
                    {workflows.map(wf => <option key={wf.id} value={wf.id}>{wf.name}</option>)}
                  </select>
                  {workflows.length === 0 && (
                    <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>No workflows yet — you can create one in the Workflows panel.</div>
                  )}
                </div>
              )}

              {actionType === 'extraction' && (
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Select Extraction <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <select value={actionId} onChange={e => setActionId(e.target.value)} style={selectStyle}>
                    <option value="">— choose an extraction —</option>
                    {searchSets.map(ss => <option key={ss.uuid} value={ss.uuid}>{ss.title}</option>)}
                  </select>
                  {searchSets.length === 0 && (
                    <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>No extractions yet — you can create one in the Extractions panel.</div>
                  )}
                </div>
              )}

              {actionType === 'task' && (
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Select Workflow Task <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <select value={actionId} onChange={e => setActionId(e.target.value)} style={selectStyle}>
                    <option value="">— choose a workflow —</option>
                    {workflows.map(wf => <option key={wf.id} value={wf.id}>{wf.name}</option>)}
                  </select>
                </div>
              )}
            </div>
          )}

          {error && (
            <div style={{
              marginTop: 14, padding: '8px 12px', fontSize: 12,
              color: '#b91c1c', backgroundColor: '#fef2f2', borderRadius: 6,
              border: '1px solid #fecaca',
            }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 28px 20px',
          borderTop: '1px solid #f3f4f6',
        }}>
          {/* Step dots */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {Array.from({ length: totalSteps }, (_, i) => i + 1).map(s => (
              <div key={s} style={{
                height: 8,
                width: s === step ? 22 : 8,
                borderRadius: 4,
                backgroundColor: s < step ? '#93c5fd' : s === step ? '#3b82f6' : '#e5e7eb',
                transition: 'all 0.2s ease',
              }} />
            ))}
          </div>

          {/* Buttons */}
          <div style={{ display: 'flex', gap: 8 }}>
            {step > 1 ? (
              <button onClick={() => setStep(s => s - 1)} disabled={creating} style={btnSecondary}>
                Back
              </button>
            ) : (
              <button onClick={onClose} style={btnSecondary}>Cancel</button>
            )}

            {step < totalSteps ? (
              <button onClick={() => setStep(s => s + 1)} disabled={!canAdvance()} style={btnPrimary(canAdvance())}>
                Next
              </button>
            ) : (
              <button onClick={handleCreate} disabled={!canAdvance() || creating} style={btnPrimary(canAdvance() && !creating)}>
                {creating && <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />}
                Create Automation
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
