import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  X, Play, Loader2, Plus, Trash2, Pencil, SlidersHorizontal,
  FileText, Filter, Outdent, Globe, Image, Code,
  Bug, Search, Zap, Download, Package, CheckCircle, XCircle,
  MousePointerClick, PenTool, ClipboardCheck, Flag,
  AlertTriangle, ChevronDown, ArrowUp, ArrowDown,
  Circle, Hand, Keyboard, Sparkles, ShieldCheck, Type,
  ArrowRight, Pause, ChevronRight, TrendingUp, RefreshCw,
  Upload,
} from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import {
  getWorkflow, addStep, deleteStep, addTask, deleteTask, updateTask,
  updateWorkflow, updateStep, downloadResults, testStep, getTestStepStatus,
  reorderSteps, validateWorkflow, runWorkflow, streamWorkflowStatus, createTempDocuments,
  getWorkflowQualityHistory, getWorkflowImprovementSuggestions,
  getValidationPlan, updateValidationPlan, generateValidationPlan,
  getValidationInputs, updateValidationInputs,
  exportWorkflowUrl, importWorkflow,
} from '../../api/workflows'
import type { ValidationCheck, ValidationResult, ValidationCheckDefinition, ValidationInputDefinition, QualityHistoryRun, BatchStatus } from '../../api/workflows'
import { listSearchSets } from '../../api/extractions'
import { getModels } from '../../api/config'
import { listContents, searchDocuments } from '../../api/documents'
import { listKnowledgeBases } from '../../api/knowledge'
import type { KnowledgeBase } from '../../types/knowledge'
import { useWorkflowRunner } from '../../hooks/useWorkflowRunner'
import type { Workflow, WorkflowStep, WorkflowTask, WorkflowStatus, SearchSet, ModelInfo } from '../../types/workflow'
import type { Document as VDoc } from '../../types/document'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

type Tab = 'design' | 'input' | 'validate'
type TaskCategory = 'all' | 'text' | 'files' | 'web' | 'output'
type TaskSubTab = 'design' | 'input' | 'output'
type TaskInputSource = 'step_input' | 'select_document' | 'workflow_documents'

interface TaskTypeDef {
  name: string
  label: string
  icon: typeof Filter
  color: string
  categories: TaskCategory[]
  enabled: boolean
}

const TASK_TYPES: TaskTypeDef[] = [
  { name: 'Extraction', label: 'Extractions', icon: Filter, color: '#dc2626', categories: ['all', 'text'], enabled: true },
  { name: 'Prompt', label: 'Prompts', icon: MousePointerClick, color: '#2563eb', categories: ['all', 'text'], enabled: true },
  { name: 'Formatter', label: 'Format', icon: Outdent, color: '#16a34a', categories: ['all', 'text'], enabled: true },
  { name: 'Browser', label: 'Browser Automation', icon: Globe, color: '#2563eb', categories: ['all', 'web'], enabled: false },
  { name: 'AddDocument', label: 'Add Document', icon: FileText, color: '#7c3aed', categories: ['all', 'files'], enabled: true },
  { name: 'AddWebsite', label: 'Add Website', icon: Globe, color: '#0891b2', categories: ['all', 'web'], enabled: true },
  { name: 'DescribeImage', label: 'Describe Image', icon: Image, color: '#ec4899', categories: ['all', 'web'], enabled: false },
  { name: 'CodeNode', label: 'Code Node', icon: Code, color: '#f59e0b', categories: ['all', 'web'], enabled: false },
  { name: 'CrawlerNode', label: 'Crawler Node', icon: Bug, color: '#84cc16', categories: ['all', 'web'], enabled: true },
  { name: 'ResearchNode', label: 'Research Node', icon: Search, color: '#8b5cf6', categories: ['all', 'web'], enabled: true },
  { name: 'KnowledgeBaseQuery', label: 'Knowledge Base Query', icon: Sparkles, color: '#0ea5e9', categories: ['all', 'text'], enabled: true },
  { name: 'APINode', label: 'API Node', icon: Zap, color: '#f97316', categories: ['all', 'web'], enabled: true },
  { name: 'DocumentRenderer', label: 'Document Renderer', icon: FileText, color: '#0d9488', categories: ['all', 'output'], enabled: true },
  { name: 'FormFiller', label: 'Form Filler', icon: MousePointerClick, color: '#e11d48', categories: ['all', 'output'], enabled: true },
  { name: 'DataExport', label: 'Data Export', icon: Download, color: '#059669', categories: ['all', 'output'], enabled: true },
  { name: 'PackageBuilder', label: 'Package Builder', icon: Package, color: '#6366f1', categories: ['all', 'output'], enabled: false },
]

const CATEGORIES: { key: TaskCategory; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'text', label: 'Text' },
  { key: 'files', label: 'Files' },
  { key: 'web', label: 'Web & Code' },
  { key: 'output', label: 'Output' },
]

const TABS: { key: Tab; label: string; icon: typeof PenTool }[] = [
  { key: 'design', label: 'Design', icon: PenTool },
  { key: 'input', label: 'Input', icon: Zap },
  { key: 'validate', label: 'Validate', icon: ClipboardCheck },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTaskColor(name: string): string {
  const found = TASK_TYPES.find(t => t.name === name)
  if (found) return found.color
  if (name === 'Format') return '#16a34a'
  return '#6b7280'
}

function getTaskIcon(name: string) {
  const found = TASK_TYPES.find(t => t.name === name)
  if (found) return found.icon
  if (name === 'Format') return Outdent
  return FileText
}

const checkerboardBg: CSSProperties = {
  backgroundColor: '#F0F2F8',
  backgroundImage: [
    'linear-gradient(45deg, #EAECF2 25%, transparent 25%)',
    'linear-gradient(-45deg, #EAECF2 25%, transparent 25%)',
    'linear-gradient(45deg, transparent 75%, #EAECF2 75%)',
    'linear-gradient(-45deg, transparent 75%, #EAECF2 75%)',
  ].join(', '),
  backgroundSize: '30px 30px',
  backgroundPosition: '0 0, 0 15px, 15px -15px, -15px 0px',
}

const TEST_MESSAGES = [
  'Preparing document...',
  'Running your task...',
  'Processing with AI...',
  'Still working...',
  'Almost there...',
]

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function WorkflowEditorPanel() {
  const { openWorkflowId, openWorkflow, closeWorkflow, selectedDocUuids, bumpActivitySignal } = useWorkspace()
  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('design')
  const [editingStepId, setEditingStepId] = useState<string | null>(null)
  const [showTaskPicker, setShowTaskPicker] = useState(false)
  const [taskPickerCategory, setTaskPickerCategory] = useState<TaskCategory>('all')
  const [showNewStepModal, setShowNewStepModal] = useState(false)
  const [newStepName, setNewStepName] = useState('')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [showDownloadPopup, setShowDownloadPopup] = useState(false)
  const [editingTask, setEditingTask] = useState<WorkflowTask | null>(null)
  const runner = useWorkflowRunner()
  const [batchMode, setBatchMode] = useState(false)
  const [runElapsed, setRunElapsed] = useState(0)
  const [textInput, setTextInput] = useState('')
  const runTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const newStepInputRef = useRef<HTMLInputElement>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  const editingStep = editingStepId
    ? workflow?.steps.find(s => s.id === editingStepId) ?? null
    : null

  // --- data fetching ---

  const refresh = useCallback(async () => {
    if (!openWorkflowId) return
    setLoading(true)
    try {
      const wf = await getWorkflow(openWorkflowId)
      setWorkflow(wf)
    } finally {
      setLoading(false)
    }
  }, [openWorkflowId])

  useEffect(() => { refresh() }, [refresh])

  // --- run elapsed timer ---

  useEffect(() => {
    if (runner.running) {
      setRunElapsed(0)
      runTimerRef.current = setInterval(() => setRunElapsed(e => e + 1), 1000)
    } else if (runTimerRef.current) {
      clearInterval(runTimerRef.current)
      runTimerRef.current = null
    }
    return () => { if (runTimerRef.current) clearInterval(runTimerRef.current) }
  }, [runner.running])

  // --- focus helpers ---

  useEffect(() => {
    if (editingTitle && titleInputRef.current) {
      titleInputRef.current.focus()
      titleInputRef.current.select()
    }
  }, [editingTitle])

  useEffect(() => {
    if (showNewStepModal && newStepInputRef.current) {
      newStepInputRef.current.focus()
    }
  }, [showNewStepModal])

  // --- handlers ---

  const handleTitleSave = async () => {
    if (!openWorkflowId || !titleValue.trim()) {
      setEditingTitle(false)
      return
    }
    await updateWorkflow(openWorkflowId, { name: titleValue.trim() })
    setEditingTitle(false)
    refresh()
  }

  const handleAddStep = async () => {
    if (!openWorkflowId || !newStepName.trim()) return
    const result = (await addStep(openWorkflowId, { name: newStepName.trim() })) as { id?: string }
    setShowNewStepModal(false)
    setNewStepName('')
    await refresh()
    if (result?.id) setEditingStepId(result.id)
  }

  const handleDeleteStep = async (stepId: string) => {
    setEditingStepId(null)
    setShowTaskPicker(false)
    await deleteStep(stepId)
    refresh()
  }

  const handleAddTask = async (taskType: TaskTypeDef) => {
    if (!editingStepId) return
    await addTask(editingStepId, { name: taskType.name })
    setShowTaskPicker(false)
    refresh()
  }

  const handleDeleteTask = async (taskId: string) => {
    await deleteTask(taskId)
    refresh()
  }

  const handleEditTask = (task: WorkflowTask) => {
    setEditingTask({ ...task, data: { ...task.data } })
  }

  const handleSaveTask = async (taskId: string, data: Record<string, unknown>) => {
    await updateTask(taskId, { data })
    setEditingTask(null)
    refresh()
  }

  const handleStepNameSave = async (stepId: string, newName: string) => {
    if (!newName.trim()) return
    await updateStep(stepId, { name: newName.trim() })
    refresh()
  }

  const handleToggleOutput = async (stepId: string, isOutput: boolean) => {
    await updateStep(stepId, { is_output: isOutput })
    refresh()
  }

  const handleMoveStep = async (stepIndex: number, direction: 'up' | 'down') => {
    if (!workflow || !openWorkflowId) return
    const steps = [...workflow.steps]
    const newIndex = direction === 'up' ? stepIndex - 1 : stepIndex + 1
    if (newIndex < 0 || newIndex >= steps.length) return
    ;[steps[stepIndex], steps[newIndex]] = [steps[newIndex], steps[stepIndex]]
    await reorderSteps(openWorkflowId, steps.map(s => s.id))
    refresh()
  }

  const isTextInput = workflow?.input_config?.trigger_type === 'text_input'

  const handleRun = async () => {
    if (!openWorkflowId) return

    if (isTextInput) {
      if (!textInput.trim()) return
      // Convert text to temp document, then combine with any selected docs
      const { document_uuids: textUuids } = await createTempDocuments(openWorkflowId, [
        { text: textInput.trim(), label: 'Text input' },
      ])
      const allUuids = [...textUuids, ...selectedDocUuids]
      setActiveTab('design')
      await runner.start(openWorkflowId, allUuids, undefined, false)
    } else {
      const uuids = selectedDocUuids.length > 0 ? selectedDocUuids : []
      if (uuids.length === 0) return
      setActiveTab('design')
      await runner.start(openWorkflowId, uuids, undefined, batchMode)
    }
  }

  // --- loading / error ---

  if (loading) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <PanelHeader title="Loading..." onClose={closeWorkflow} />
        <div style={{ padding: 40, textAlign: 'center', color: '#888', fontSize: 13 }}>Loading workflow...</div>
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <PanelHeader title="Workflow" onClose={closeWorkflow} />
        <div style={{ padding: 40, textAlign: 'center', color: '#d93025', fontSize: 13 }}>Workflow not found.</div>
      </div>
    )
  }

  // --- tab badge counts ---
  const inputBadge = 0

  // --- render ---

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: '#fff', position: 'relative' }}>
      {/* ===== VERIFIED WORKFLOW NOTICE ===== */}
      {workflow.steps.length > 0 && (workflow as Workflow & { verified?: boolean }).verified && (
        <div style={{
          margin: '8px 24px 0', padding: '8px 12px', fontSize: 12, color: '#a16c2d',
          backgroundColor: '#fef3c7', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0 }} />
          Verified workflows are view-only unless you are an examiner. Clone the workflow to make changes.
        </div>
      )}

      {/* ===== HEADER ===== */}
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
              onClick={() => { setTitleValue(workflow.name); setEditingTitle(true) }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, color: '#202124', letterSpacing: '-0.01em' }}>
                {workflow.name}
              </span>
              <Pencil style={{ width: 14, height: 14, color: '#9ca3af' }} />
            </div>
          )}
          <button
            onClick={() => window.open(exportWorkflowUrl(workflow.id), '_blank')}
            title="Export workflow"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#5f6368', display: 'flex', flexShrink: 0 }}
          >
            <Download style={{ width: 16, height: 16 }} />
          </button>
          <button
            onClick={() => importInputRef.current?.click()}
            title="Import workflow"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#5f6368', display: 'flex', flexShrink: 0 }}
          >
            <Upload style={{ width: 16, height: 16 }} />
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".json"
            style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0]
              if (!f) return
              e.target.value = ''
              try {
                const result = await importWorkflow(f, workflow.space || 'default')
                openWorkflow(result.id)
              } catch (err: unknown) {
                alert(err instanceof Error ? err.message : 'Import failed')
              }
            }}
          />
          <button
            onClick={closeWorkflow}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, color: '#5f6368', display: 'flex', flexShrink: 0 }}
          >
            <X style={{ width: 20, height: 20 }} />
          </button>
        </div>
        {workflow.description && (
          <div style={{ fontSize: 13, color: '#5f6368', marginTop: 4 }}>{workflow.description}</div>
        )}
      </div>

      {/* ===== TAB BAR ===== */}
      <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', padding: '0 24px', backgroundColor: '#fff', flexShrink: 0 }}>
        {TABS.map(tab => {
          const TabIcon = tab.icon
          const badge = tab.key === 'input' ? inputBadge : 0
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '12px 20px', fontSize: 13,
                fontWeight: activeTab === tab.key ? 700 : 500,
                fontFamily: 'inherit', background: 'none', border: 'none',
                borderBottom: activeTab === tab.key
                  ? '3px solid var(--highlight-color, #eab308)'
                  : '3px solid transparent',
                color: activeTab === tab.key
                  ? 'var(--highlight-color, #eab308)'
                  : '#6b7280',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                position: 'relative',
              }}
            >
              <TabIcon style={{ width: 14, height: 14 }} />
              {tab.label}
              {badge > 0 && (
                <span style={{
                  minWidth: 18, height: 18, borderRadius: 9, fontSize: 10, fontWeight: 700,
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  padding: '0 5px',
                }}>
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* ===== TAB CONTENT ===== */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {activeTab === 'design' && (
          <DesignCanvas
            workflow={workflow}
            selectedDocCount={selectedDocUuids.length}
            runnerStatus={runner.status}
            runnerRunning={runner.running}
            runnerSessionId={runner.sessionId}
            batchStatus={runner.batchStatus}
            runElapsed={runElapsed}
            showDownloadPopup={showDownloadPopup}
            setShowDownloadPopup={setShowDownloadPopup}
            onClickStep={setEditingStepId}
            onAddStep={() => { setNewStepName(''); setShowNewStepModal(true) }}
            onMoveStep={handleMoveStep}
          />
        )}

        {activeTab === 'input' && <InputTab workflow={workflow} openWorkflowId={openWorkflowId} onRefresh={refresh} />}
        {activeTab === 'validate' && <ValidateTab workflowId={openWorkflowId} selectedDocUuids={selectedDocUuids} />}
      </div>

      {/* ===== BOTTOM TOOLBAR (Run) ===== */}
      <div style={{ flexShrink: 0, padding: 15, backgroundColor: '#fff', boxShadow: '0 0px 23px -8px rgb(211,211,211)' }}>
        {isTextInput ? (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Type style={{ width: 14, height: 14 }} />
              Text Input
            </div>
            <textarea
              value={textInput}
              onChange={e => setTextInput(e.target.value)}
              placeholder="Paste or type the text to process..."
              rows={4}
              style={{
                width: '100%', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px',
                resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            {selectedDocUuids.length > 0 && (
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                <FileText style={{ width: 12, height: 12 }} />
                + {selectedDocUuids.length} document{selectedDocUuids.length !== 1 ? 's' : ''} selected
              </div>
            )}
          </div>
        ) : (
          selectedDocUuids.length > 1 && (
            <label style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
              fontSize: 13, color: '#374151', cursor: 'pointer', userSelect: 'none',
            }}>
              <input
                type="checkbox"
                checked={batchMode}
                onChange={e => setBatchMode(e.target.checked)}
                style={{ accentColor: 'var(--highlight-color, #eab308)' }}
              />
              Run per document ({selectedDocUuids.length} runs)
            </label>
          )
        )}
        <button
          onClick={handleRun}
          disabled={runner.running || (isTextInput ? !textInput.trim() : selectedDocUuids.length === 0)}
          style={{
            width: '100%', padding: '12px 16px', fontSize: 14, fontWeight: 700,
            fontFamily: 'inherit', borderRadius: 'var(--ui-radius, 8px)', border: 'none',
            backgroundColor: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            cursor: runner.running || (isTextInput ? !textInput.trim() : selectedDocUuids.length === 0) ? 'not-allowed' : 'pointer',
            opacity: (isTextInput ? !textInput.trim() : selectedDocUuids.length === 0) && !runner.running ? 0.5 : 1,
            textTransform: 'uppercase', letterSpacing: '0.05em',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          {runner.running ? (
            <>
              <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite' }} />
              WORKFLOW RUNNING
            </>
          ) : (
            <>
              <Play style={{ width: 16, height: 16 }} />
              RUN
            </>
          )}
        </button>
      </div>

      {/* ===== EDIT STEP OVERLAY ===== */}
      {editingStep && (
        <EditStepOverlay
          step={editingStep}
          onClose={() => { setEditingStepId(null); setShowTaskPicker(false) }}
          onDeleteStep={() => handleDeleteStep(editingStep.id)}
          onAddTask={() => { setTaskPickerCategory('all'); setShowTaskPicker(true) }}
          onEditTask={handleEditTask}
          onDeleteTask={handleDeleteTask}
          onStepNameSave={handleStepNameSave}
          onToggleOutput={handleToggleOutput}
          showTaskPicker={showTaskPicker}
          taskPickerCategory={taskPickerCategory}
          setTaskPickerCategory={setTaskPickerCategory}
          onSelectTaskType={handleAddTask}
          onCloseTaskPicker={() => setShowTaskPicker(false)}
        />
      )}

      {/* ===== TASK EDIT MODAL ===== */}
      {editingTask && (
        <TaskEditModal
          task={editingTask}
          selectedDocUuids={selectedDocUuids}
          onClose={() => setEditingTask(null)}
          onSave={handleSaveTask}
        />
      )}

      {/* ===== NEW STEP MODAL ===== */}
      {showNewStepModal && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1000,
          backgroundColor: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            backgroundColor: '#fff', borderRadius: 'var(--ui-radius, 8px)', padding: 24,
            width: 340, boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#202124', marginBottom: 16 }}>New Step</div>
            <input
              ref={newStepInputRef}
              value={newStepName}
              onChange={e => setNewStepName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleAddStep() }}
              placeholder="Step name..."
              style={{
                width: '100%', padding: '10px 12px', fontSize: 14, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, outline: 'none', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowNewStepModal(false)}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                  border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                  cursor: 'pointer', color: '#374151',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleAddStep}
                disabled={!newStepName.trim()}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                  border: 'none', borderRadius: 6,
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  cursor: newStepName.trim() ? 'pointer' : 'not-allowed',
                  opacity: newStepName.trim() ? 1 : 0.5,
                }}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keyframe animations */}
      <style>{`
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Simple header for loading/error states
// ---------------------------------------------------------------------------

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }) {
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

// ---------------------------------------------------------------------------
// Design canvas — checkerboard + vertical step chain
// ---------------------------------------------------------------------------

function DesignCanvas({
  workflow,
  selectedDocCount,
  runnerStatus,
  runnerRunning,
  runnerSessionId,
  batchStatus,
  runElapsed,
  showDownloadPopup,
  setShowDownloadPopup,
  onClickStep,
  onAddStep,
  onMoveStep,
}: {
  workflow: Workflow
  selectedDocCount: number
  runnerStatus: WorkflowStatus | null
  runnerRunning: boolean
  runnerSessionId: string | null
  batchStatus: BatchStatus | null
  runElapsed: number
  showDownloadPopup: boolean
  setShowDownloadPopup: (v: boolean) => void
  onClickStep: (stepId: string) => void
  onAddStep: () => void
  onMoveStep: (stepIndex: number, direction: 'up' | 'down') => void
}) {
  return (
    <div style={{
      ...checkerboardBg,
      border: '1px solid #2f2f2fc2',
      padding: '30px 30px 150px 30px',
      minHeight: '100%',
    }}>
      {/* Trigger pill */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          backgroundColor: '#404040', color: '#fff', fontSize: 12, fontWeight: 600,
          padding: '6px 0', width: 120, textAlign: 'center', borderRadius: 20,
        }}>
          Trigger
        </div>
      </div>

      <ConnectionLine />

      {/* Input card — adapts to trigger type */}
      <div style={{
        backgroundColor: '#fff', border: '2px solid var(--highlight-color, #eab308)',
        borderRadius: 'var(--ui-radius, 8px)', padding: 15, textAlign: 'center',
        boxShadow: '0 6px 18px rgba(0,0,0,0.05)',
      }}>
        {workflow.input_config?.trigger_type === 'text_input' ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <Type style={{ width: 16, height: 16, color: 'var(--highlight-color, #eab308)' }} />
              <span style={{ fontWeight: 600, fontSize: 14 }}>Text Input</span>
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              Text provided at run time
              {selectedDocCount > 0 && ` + ${selectedDocCount} document${selectedDocCount !== 1 ? 's' : ''}`}
            </div>
          </>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <FileText style={{ width: 16, height: 16, color: 'var(--highlight-color, #eab308)' }} />
              <span style={{ fontWeight: 600, fontSize: 14 }}>Documents Selected</span>
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              {selectedDocCount} document{selectedDocCount !== 1 ? 's' : ''} selected
            </div>
          </>
        )}
      </div>

      {/* Step cards */}
      {workflow.steps.map((step, idx) => (
        <div key={step.id}>
          <ConnectionLine />
          <StepCard
            step={step}
            index={idx}
            totalSteps={workflow.steps.length}
            isActive={runnerRunning && runnerStatus?.current_step_name === step.name}
            onClick={() => onClickStep(step.id)}
            onMoveUp={() => onMoveStep(idx, 'up')}
            onMoveDown={() => onMoveStep(idx, 'down')}
          />
        </div>
      ))}

      {/* +ADD STEP — hidden when the last step is an output step */}
      {!(workflow.steps.length > 0 && workflow.steps[workflow.steps.length - 1].is_output) && (
        <>
          <ConnectionLine />
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button
              onClick={onAddStep}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '10px 24px',
                backgroundColor: 'var(--highlight-color, #eab308)',
                color: 'var(--highlight-text-color, #000)',
                border: 'none', borderRadius: 'var(--ui-radius, 8px)',
                fontSize: 13, fontWeight: 700, cursor: 'pointer',
              }}
            >
              <Plus style={{ width: 16, height: 16 }} />
              ADD STEP
            </button>
          </div>
        </>
      )}

      {/* Workflow output (during/after run) */}
      {(runnerRunning || runnerStatus) && !batchStatus && (
        <>
          <ConnectionLine />
          <WorkflowOutputCard
            status={runnerStatus}
            sessionId={runnerSessionId}
            running={runnerRunning}
            runElapsed={runElapsed}
            showDownloadPopup={showDownloadPopup}
            setShowDownloadPopup={setShowDownloadPopup}
          />
        </>
      )}

      {/* Batch output (during/after batch run) */}
      {batchStatus && (
        <>
          <ConnectionLine />
          <BatchOutputCard
            batchStatus={batchStatus}
            running={runnerRunning}
            runElapsed={runElapsed}
          />
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Connection line + semicircle connector
// ---------------------------------------------------------------------------

function ConnectionLine() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ width: 2, height: 20, backgroundColor: '#bcbcbc' }} />
    </div>
  )
}

function Connector({ position }: { position: 'top' | 'bottom' }) {
  const isTop = position === 'top'
  return (
    <div style={{
      position: 'absolute', left: '50%', transform: 'translateX(-50%)',
      ...(isTop ? { top: -10 } : { bottom: -10 }),
      width: 22, height: 11,
      border: '2px solid #e0e0e0',
      ...(isTop
        ? { borderBottom: 'none', borderRadius: '11px 11px 0 0' }
        : { borderTop: 'none', borderRadius: '0 0 11px 11px' }),
      backgroundColor: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        width: 5, height: 5, borderRadius: '50%', backgroundColor: '#d1d5db',
        ...(isTop ? { marginTop: 2 } : { marginBottom: 2 }),
      }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step card
// ---------------------------------------------------------------------------

function StepCard({ step, index, totalSteps, isActive, onClick, onMoveUp, onMoveDown }: {
  step: WorkflowStep
  index: number
  totalSteps: number
  isActive: boolean
  onClick: () => void
  onMoveUp: () => void
  onMoveDown: () => void
}) {
  const isOutput = step.is_output
  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        backgroundColor: isOutput ? undefined : '#fff',
        ...(isOutput ? { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' } : {}),
        boxShadow: '0 6px 18px rgba(0,0,0,0.05)',
        borderRadius: 'var(--ui-radius, 8px)',
        padding: 15, cursor: 'pointer',
        border: isActive ? '2px solid var(--highlight-color, #eab308)' : '2px solid transparent',
        transition: 'border-color 0.2s',
        marginTop: 10, marginBottom: 10,
      }}
    >
      <Connector position="top" />
      <Connector position="bottom" />
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 6,
          backgroundColor: isOutput ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          {isOutput ? (
            <Flag style={{ width: 18, height: 18, color: '#fff' }} />
          ) : (
            <span style={{ fontSize: 18, fontWeight: 700, color: '#374151' }}>{index + 1}</span>
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: isOutput ? '#fff' : '#202124' }}>
            {isOutput ? 'WORKFLOW OUTPUT' : step.name}
            {isActive && (
              <Loader2 style={{
                width: 14, height: 14, marginLeft: 8,
                animation: 'spin 1s linear infinite',
                display: 'inline', verticalAlign: 'middle',
                color: isOutput ? '#fff' : 'var(--highlight-color, #eab308)',
              }} />
            )}
          </div>
          <div style={{ fontSize: 12, color: isOutput ? 'rgba(255,255,255,0.7)' : '#6b7280', marginTop: 2 }}>
            {isOutput ? step.name : `${step.tasks.length} task${step.tasks.length !== 1 ? 's' : ''}`}
          </div>
        </div>
        {/* Move up/down buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
          <button
            onClick={onMoveUp}
            disabled={index === 0}
            style={{
              background: 'none', border: 'none', cursor: index === 0 ? 'default' : 'pointer',
              padding: 2, display: 'flex',
              color: isOutput ? 'rgba(255,255,255,0.4)' : '#d1d5db',
              opacity: index === 0 ? 0.3 : 1,
            }}
          >
            <ArrowUp style={{ width: 14, height: 14 }} />
          </button>
          <button
            onClick={onMoveDown}
            disabled={index === totalSteps - 1}
            style={{
              background: 'none', border: 'none', cursor: index === totalSteps - 1 ? 'default' : 'pointer',
              padding: 2, display: 'flex',
              color: isOutput ? 'rgba(255,255,255,0.4)' : '#d1d5db',
              opacity: index === totalSteps - 1 ? 0.3 : 1,
            }}
          >
            <ArrowDown style={{ width: 14, height: 14 }} />
          </button>
        </div>
        <SlidersHorizontal style={{
          width: 16, height: 16,
          color: isOutput ? 'rgba(255,255,255,0.6)' : '#9ca3af',
          flexShrink: 0,
        }} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Edit step overlay (with inline step name editing)
// ---------------------------------------------------------------------------

function EditStepOverlay({
  step, onClose, onDeleteStep, onAddTask, onEditTask, onDeleteTask,
  onStepNameSave, onToggleOutput,
  showTaskPicker, taskPickerCategory, setTaskPickerCategory,
  onSelectTaskType, onCloseTaskPicker,
}: {
  step: WorkflowStep
  onClose: () => void
  onDeleteStep: () => void
  onAddTask: () => void
  onEditTask: (task: WorkflowTask) => void
  onDeleteTask: (taskId: string) => void
  onStepNameSave: (stepId: string, newName: string) => void
  onToggleOutput: (stepId: string, isOutput: boolean) => void
  showTaskPicker: boolean
  taskPickerCategory: TaskCategory
  setTaskPickerCategory: (cat: TaskCategory) => void
  onSelectTaskType: (type: TaskTypeDef) => void
  onCloseTaskPicker: () => void
}) {
  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState(step.name)
  const nameInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editingName && nameInputRef.current) {
      nameInputRef.current.focus()
      nameInputRef.current.select()
    }
  }, [editingName])

  const handleNameSave = () => {
    if (nameValue.trim() && nameValue.trim() !== step.name) {
      onStepNameSave(step.id, nameValue.trim())
    }
    setEditingName(false)
  }

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1000,
      backgroundColor: '#fff', display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {editingName ? (
            <input
              ref={nameInputRef}
              value={nameValue}
              onChange={e => setNameValue(e.target.value)}
              onBlur={handleNameSave}
              onKeyDown={e => {
                if (e.key === 'Enter') handleNameSave()
                if (e.key === 'Escape') { setNameValue(step.name); setEditingName(false) }
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
              onClick={() => { setNameValue(step.name); setEditingName(true) }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, color: '#202124' }}>{step.name}</span>
              <Pencil style={{ width: 14, height: 14, color: '#9ca3af' }} />
            </div>
          )}
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex',
          }}>
            <X style={{ width: 20, height: 20 }} />
          </button>
        </div>
        <div style={{ fontSize: 13, color: '#5f6368', marginTop: 4 }}>Build this step of the workflow</div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 24px 200px' }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: '#6b7280',
          textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12,
        }}>
          Basic Setup
        </div>

        {/* Output step toggle */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
          cursor: 'pointer', padding: '10px 14px',
          border: step.is_output ? '2px solid #7c3aed' : '1px solid #e5e7eb',
          borderRadius: 8, backgroundColor: step.is_output ? '#f5f3ff' : '#fff',
        }}>
          <input
            type="checkbox"
            checked={step.is_output}
            onChange={e => onToggleOutput(step.id, e.target.checked)}
            style={{ accentColor: '#7c3aed' }}
          />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: step.is_output ? '#7c3aed' : '#374151' }}>
              Output Step
            </div>
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 1 }}>
              Mark this as the final output step of the workflow
            </div>
          </div>
        </label>

        {/* Task list in checkerboard container */}
        <div style={{
          ...checkerboardBg,
          border: '1px solid #2f2f2fc2',
          borderRadius: 'var(--ui-radius, 8px)',
          padding: 20,
        }}>
          {step.tasks.map(task => {
            const color = getTaskColor(task.name)
            const Icon = getTaskIcon(task.name)
            return (
              <div
                key={task.id}
                onClick={() => onEditTask(task)}
                style={{
                  backgroundColor: '#fff', borderRadius: 'var(--ui-radius, 8px)',
                  padding: 12, marginBottom: 8,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                  display: 'flex', alignItems: 'center', gap: 10,
                  cursor: 'pointer',
                }}
              >
                <div style={{
                  width: 32, height: 32, borderRadius: 6,
                  backgroundColor: color + '18',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <Icon style={{ width: 16, height: 16, color }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>{task.name}</div>
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 1 }}>
                    {task.name === 'Extraction' ? 'Structured data extraction'
                      : task.name === 'Prompt' ? 'LLM prompt task'
                      : task.name === 'Formatter' || task.name === 'Format' ? 'Format output'
                      : task.name === 'AddWebsite' ? 'Fetch URL text'
                      : task.name === 'AddDocument' ? 'Add document text'
                      : task.name === 'DescribeImage' ? 'AI image description'
                      : task.name === 'CodeNode' ? 'Run Python code'
                      : task.name === 'CrawlerNode' ? 'Web crawler'
                      : task.name === 'ResearchNode' ? 'Deep AI research'
                      : task.name === 'KnowledgeBaseQuery' ? 'Search knowledge base'
                      : task.name === 'APINode' ? 'HTTP API request'
                      : task.name === 'DocumentRenderer' ? 'Render document'
                      : task.name === 'FormFiller' ? 'Fill template'
                      : task.name === 'DataExport' ? 'Export data'
                      : task.name === 'PackageBuilder' ? 'Build zip package'
                      : task.name}
                  </div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); onDeleteTask(task.id) }} style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex',
                }}>
                  <Trash2 style={{ width: 14, height: 14 }} />
                </button>
              </div>
            )
          })}

          {/* Add task button */}
          <div
            onClick={onAddTask}
            style={{
              backgroundColor: '#191919', color: '#fff',
              borderRadius: 'var(--ui-radius, 8px)',
              padding: 16, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 10,
              marginTop: step.tasks.length > 0 ? 8 : 0,
            }}
          >
            <Plus style={{ width: 18, height: 18 }} />
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {step.tasks.length > 0 ? 'ADD A TASK' : 'ADD YOUR FIRST TASK'}
            </span>
          </div>
        </div>
      </div>

      {/* Bottom toolbar */}
      <div style={{
        flexShrink: 0, padding: 15, backgroundColor: '#fff',
        boxShadow: '0 0px 23px -8px rgb(211,211,211)',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <button
          onClick={onDeleteStep}
          style={{
            padding: '10px 20px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
            border: '1px solid #fca5a5', borderRadius: 'var(--ui-radius, 8px)',
            backgroundColor: '#fff', color: '#dc2626', cursor: 'pointer',
          }}
        >
          Delete Step
        </button>
        <button
          onClick={onClose}
          style={{
            padding: '10px 24px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
            border: 'none', borderRadius: 'var(--ui-radius, 8px)',
            backgroundColor: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            cursor: 'pointer', textTransform: 'uppercase',
          }}
        >
          DONE
        </button>
      </div>

      {/* Task type picker overlay (nested) */}
      {showTaskPicker && (
        <TaskTypePicker
          category={taskPickerCategory}
          setCategory={setTaskPickerCategory}
          onSelect={onSelectTaskType}
          onClose={onCloseTaskPicker}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Task type picker (categorized)
// ---------------------------------------------------------------------------

function TaskTypePicker({ category, setCategory, onSelect, onClose }: {
  category: TaskCategory
  setCategory: (cat: TaskCategory) => void
  onSelect: (type: TaskTypeDef) => void
  onClose: () => void
}) {
  const filteredTypes = TASK_TYPES.filter(t =>
    category === 'all' ? true : t.categories.includes(category)
  )

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1001,
      backgroundColor: '#fff', display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 18, fontWeight: 600, color: '#202124' }}>Add a Task</span>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex',
          }}>
            <X style={{ width: 20, height: 20 }} />
          </button>
        </div>
      </div>

      {/* Two-column layout */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* Category sidebar */}
        <div style={{
          width: '25%', backgroundColor: '#f4f4f4',
          borderRight: '1px solid #e5e7eb', padding: '16px 0', overflowY: 'auto',
        }}>
          {CATEGORIES.map(cat => (
            <button
              key={cat.key}
              onClick={() => setCategory(cat.key)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '10px 20px', fontSize: 13,
                fontWeight: category === cat.key ? 700 : 500,
                fontFamily: 'inherit',
                background: category === cat.key ? '#fff' : 'none',
                border: 'none', cursor: 'pointer',
                color: category === cat.key ? '#202124' : '#6b7280',
                borderRight: category === cat.key
                  ? '2px solid var(--highlight-color, #eab308)'
                  : '2px solid transparent',
              }}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Task cards grid */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          {/* Enabled tasks */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: 12,
          }}>
            {filteredTypes.filter(t => t.enabled).map(taskType => {
              const Icon = taskType.icon
              return (
                <button
                  key={taskType.name}
                  onClick={() => onSelect(taskType)}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                    padding: 16, border: '1px solid #e5e7eb',
                    borderRadius: 'var(--ui-radius, 8px)',
                    backgroundColor: '#fff',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'box-shadow 0.15s',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.boxShadow = 'none'
                  }}
                >
                  <div style={{
                    width: 40, height: 40, borderRadius: 8,
                    backgroundColor: taskType.color + '15',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon style={{ width: 20, height: 20, color: taskType.color }} />
                  </div>
                  <span style={{
                    fontSize: 12, fontWeight: 600, textAlign: 'center',
                    color: '#202124',
                  }}>
                    {taskType.label}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Coming Soon section */}
          {filteredTypes.some(t => !t.enabled) && (
            <>
              <div style={{
                margin: '24px 0 12px', fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                color: '#9ca3af', letterSpacing: '0.5px',
              }}>
                Coming Soon
              </div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                gap: 12,
              }}>
                {filteredTypes.filter(t => !t.enabled).map(taskType => {
                  const Icon = taskType.icon
                  return (
                    <button
                      key={taskType.name}
                      disabled
                      style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                        padding: 16, border: '1px solid #e5e7eb',
                        borderRadius: 'var(--ui-radius, 8px)',
                        backgroundColor: '#fff',
                        cursor: 'default',
                        opacity: 0.4,
                        fontFamily: 'inherit',
                      }}
                    >
                      <div style={{
                        width: 40, height: 40, borderRadius: 8,
                        backgroundColor: '#f3f4f6',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Icon style={{ width: 20, height: 20, color: '#9ca3af' }} />
                      </div>
                      <span style={{
                        fontSize: 12, fontWeight: 600, textAlign: 'center',
                        color: '#9ca3af',
                      }}>
                        {taskType.label}
                      </span>
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Task edit modal (with Design/Input/Output sub-tabs + test step)
// ---------------------------------------------------------------------------

function TaskEditModal({ task, selectedDocUuids, onClose, onSave }: {
  task: WorkflowTask
  selectedDocUuids: string[]
  onClose: () => void
  onSave: (taskId: string, data: Record<string, unknown>) => void
}) {
  const [taskData, setTaskData] = useState<Record<string, unknown>>({ ...task.data })
  const [saving, setSaving] = useState(false)
  const [subTab, setSubTab] = useState<TaskSubTab>('design')

  // Input source config
  const [inputSource, setInputSource] = useState<TaskInputSource>(
    (task.data.input_source as TaskInputSource) || 'step_input'
  )
  const [selectedDocUuid, setSelectedDocUuid] = useState<string>(
    (task.data.selected_document_uuid as string) || ''
  )
  const [docSearchQuery, setDocSearchQuery] = useState('')
  const [docSearchResults, setDocSearchResults] = useState<VDoc[]>([])
  const [showDocDropdown, setShowDocDropdown] = useState(false)

  // Output post-process
  const [postProcessEnabled, setPostProcessEnabled] = useState(
    !!(task.data.post_process_prompt)
  )
  const [postProcessPrompt, setPostProcessPrompt] = useState(
    (task.data.post_process_prompt as string) || ''
  )

  // Saved extraction sets dropdown
  const [savedSets, setSavedSets] = useState<SearchSet[]>([])
  const [loadingSets, setLoadingSets] = useState(false)

  // Model override for LLM tasks
  const LLM_TASKS = ['Extraction', 'Prompt', 'Formatter', 'DescribeImage', 'ResearchNode', 'FormFiller', 'Browser']
  const [models, setModels] = useState<ModelInfo[]>([])

  // Knowledge base list for KnowledgeBaseQuery tasks
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])

  // Test step
  const [testing, setTesting] = useState(false)
  const [testProgress, setTestProgress] = useState(0)
  const [testMessage, setTestMessage] = useState('')
  const [testResult, setTestResult] = useState<unknown>(null)
  const [testError, setTestError] = useState<string | null>(null)
  const testIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const testMsgRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const color = getTaskColor(task.name)
  const Icon = getTaskIcon(task.name)

  // Load saved extraction sets for Extraction tasks
  useEffect(() => {
    if (task.name === 'Extraction') {
      setLoadingSets(true)
      listSearchSets().then(sets => setSavedSets(sets)).catch(() => {}).finally(() => setLoadingSets(false))
    }
  }, [task.name])

  // Load models for LLM task types
  useEffect(() => {
    if (LLM_TASKS.includes(task.name)) {
      getModels().then(setModels).catch(() => {})
    }
  }, [task.name])

  // Load knowledge bases for KnowledgeBaseQuery tasks
  useEffect(() => {
    if (task.name === 'KnowledgeBaseQuery') {
      listKnowledgeBases().then(setKnowledgeBases).catch(() => {})
    }
  }, [task.name])

  // Document search debounce
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!docSearchQuery.trim()) {
      setDocSearchResults([])
      setShowDocDropdown(false)
      return
    }
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const res = await listContents('default')
        const filtered = res.documents.filter(d =>
          d.title.toLowerCase().includes(docSearchQuery.toLowerCase())
        )
        setDocSearchResults(filtered.slice(0, 10))
        setShowDocDropdown(true)
      } catch { /* ignore */ }
    }, 300)
    return () => { if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current) }
  }, [docSearchQuery])

  // Cleanup test intervals on unmount
  useEffect(() => {
    return () => {
      if (testIntervalRef.current) clearInterval(testIntervalRef.current)
      if (testMsgRef.current) clearInterval(testMsgRef.current)
    }
  }, [])

  const handleUpdate = async () => {
    setSaving(true)
    try {
      const finalData = {
        ...taskData,
        input_source: inputSource,
        ...(inputSource === 'select_document' ? { selected_document_uuid: selectedDocUuid } : {}),
        ...(postProcessEnabled ? { post_process_prompt: postProcessPrompt } : { post_process_prompt: undefined }),
      }
      onSave(task.id, finalData)
    } finally {
      setSaving(false)
    }
  }

  const handleTestStep = async () => {
    if (selectedDocUuids.length === 0) return
    setTesting(true)
    setTestProgress(0)
    setTestResult(null)
    setTestError(null)
    setTestMessage(TEST_MESSAGES[0])

    // Cycle messages
    let msgIdx = 0
    testMsgRef.current = setInterval(() => {
      msgIdx = (msgIdx + 1) % TEST_MESSAGES.length
      setTestMessage(TEST_MESSAGES[msgIdx])
    }, 3000)

    try {
      const { task_id } = await testStep({
        task_name: task.name,
        task_data: taskData,
        document_uuids: selectedDocUuids.slice(0, 1),
      })

      // Poll for test result
      testIntervalRef.current = setInterval(async () => {
        try {
          const res = await getTestStepStatus(task_id)
          if (res.status === 'completed' || res.status === 'error' || res.status === 'failed') {
            if (testIntervalRef.current) { clearInterval(testIntervalRef.current); testIntervalRef.current = null }
            if (testMsgRef.current) { clearInterval(testMsgRef.current); testMsgRef.current = null }
            setTesting(false)
            setTestProgress(100)
            if (res.status === 'completed') {
              setTestResult(res.result)
            } else {
              setTestError('Test failed. Please check your configuration.')
            }
          } else {
            setTestProgress(prev => Math.min(prev + 8, 90))
          }
        } catch {
          // Keep polling
        }
      }, 2000)
    } catch (err) {
      setTesting(false)
      setTestError(err instanceof Error ? err.message : 'Failed to start test')
      if (testMsgRef.current) { clearInterval(testMsgRef.current); testMsgRef.current = null }
    }
  }

  const getTextValue = (key: string): string => {
    const val = taskData[key]
    if (typeof val === 'string') return val
    return ''
  }

  const setTextValue = (key: string, value: string) => {
    setTaskData(prev => ({ ...prev, [key]: value }))
  }

  const handleSelectSavedSet = (uuid: string) => {
    const set = savedSets.find(s => s.uuid === uuid)
    if (set) {
      setTaskData(prev => ({ ...prev, search_set_uuid: uuid, name: set.title || prev.name }))
    }
  }

  const SUB_TABS: { key: TaskSubTab; label: string }[] = [
    { key: 'design', label: 'Design' },
    { key: 'input', label: 'Input' },
    { key: 'output', label: 'Output' },
  ]

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 1002,
      backgroundColor: '#fff', display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid #e5e7eb', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 6,
              backgroundColor: color + '18',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Icon style={{ width: 16, height: 16, color }} />
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#202124' }}>{task.name}</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 1 }}>
                {task.name === 'Extraction' ? 'Extract specific information from text using AI'
                  : task.name === 'Prompt' ? 'Uses AI to perform your instructions on text'
                  : task.name === 'Formatter' || task.name === 'Format' ? 'Format and structure output data'
                  : task.name === 'AddWebsite' ? 'Fetch a URL and pass its text downstream'
                  : task.name === 'AddDocument' ? 'Insert a document\'s text mid-workflow'
                  : task.name === 'DescribeImage' ? 'Describe an image using AI'
                  : task.name === 'CodeNode' ? 'Run Python code on input data'
                  : task.name === 'CrawlerNode' ? 'Crawl multiple pages from a starting URL'
                  : task.name === 'ResearchNode' ? 'Deep multi-pass AI analysis'
                  : task.name === 'KnowledgeBaseQuery' ? 'Search a knowledge base and inject results as context'
                  : task.name === 'APINode' ? 'Make HTTP API requests'
                  : task.name === 'DocumentRenderer' ? 'Render output as a downloadable file'
                  : task.name === 'FormFiller' ? 'Fill a template with data'
                  : task.name === 'DataExport' ? 'Export structured data as a file'
                  : task.name === 'PackageBuilder' ? 'Bundle outputs into a zip'
                  : 'Configure this task'}
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex',
          }}>
            <X style={{ width: 20, height: 20 }} />
          </button>
        </div>

        {/* Sub-tab bar */}
        <div style={{ display: 'flex', gap: 0, marginTop: 12 }}>
          {SUB_TABS.map(st => (
            <button
              key={st.key}
              onClick={() => setSubTab(st.key)}
              style={{
                padding: '8px 16px', fontSize: 12, fontWeight: subTab === st.key ? 700 : 500,
                fontFamily: 'inherit', background: 'none', border: 'none',
                borderBottom: subTab === st.key
                  ? '2px solid var(--highlight-color, #eab308)'
                  : '2px solid transparent',
                color: subTab === st.key ? 'var(--highlight-color, #eab308)' : '#6b7280',
                cursor: 'pointer',
              }}
            >
              {st.label}
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
        {/* ===== DESIGN SUB-TAB ===== */}
        {subTab === 'design' && (
          <div>
            {task.name === 'Extraction' && (
              <div>
                {/* Saved extraction sets dropdown */}
                {savedSets.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                      Use Saved Extraction Set
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        value={getTextValue('search_set_uuid')}
                        onChange={e => handleSelectSavedSet(e.target.value)}
                        style={{
                          width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                          border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                          color: '#374151', appearance: 'none', paddingRight: 32,
                        }}
                      >
                        <option value="">Select an extraction set...</option>
                        {savedSets.map(s => (
                          <option key={s.uuid} value={s.uuid}>{s.title}</option>
                        ))}
                      </select>
                      <ChevronDown style={{
                        position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                        width: 14, height: 14, color: '#9ca3af', pointerEvents: 'none',
                      }} />
                    </div>
                    {loadingSets && (
                      <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>Loading saved sets...</div>
                    )}
                  </div>
                )}

                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                    Enter extractions (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={getTextValue('extractions')}
                    onChange={e => setTextValue('extractions', e.target.value)}
                    placeholder="e.g., Name, Age, Location"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>

                {taskData.search_set_uuid && (
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
                    <span style={{ fontWeight: 600 }}>Linked extraction:</span>{' '}
                    <span style={{ fontFamily: 'monospace', fontSize: 11 }}>
                      {String(taskData.search_set_uuid)}
                    </span>
                  </div>
                )}

                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                    Extraction Name
                  </label>
                  <input
                    type="text"
                    value={getTextValue('name')}
                    onChange={e => setTextValue('name', e.target.value)}
                    placeholder="Name for this extraction task"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'Prompt' && (
              <div>
                <label style={{
                  display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8,
                }}>
                  Prompt
                </label>
                <textarea
                  value={getTextValue('prompt')}
                  onChange={e => setTextValue('prompt', e.target.value)}
                  placeholder="e.g., Summarize this for me into a todo list"
                  rows={10}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 14,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                    lineHeight: 1.5,
                  }}
                />
              </div>
            )}

            {(task.name === 'Formatter' || task.name === 'Format') && (
              <div>
                <label style={{
                  display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8,
                }}>
                  Format Template
                </label>
                <textarea
                  value={getTextValue('format_template')}
                  onChange={e => setTextValue('format_template', e.target.value)}
                  placeholder="Enter your format template..."
                  rows={10}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 14,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                    lineHeight: 1.5,
                  }}
                />
              </div>
            )}

            {task.name === 'Browser' && (
              <BrowserAutomationDesign taskData={taskData} setTextValue={setTextValue} getTextValue={getTextValue} setTaskData={setTaskData} />
            )}

            {task.name === 'AddWebsite' && (
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  URL
                </label>
                <input
                  type="text"
                  value={getTextValue('url')}
                  onChange={e => setTextValue('url', e.target.value)}
                  placeholder="https://example.com"
                  style={{
                    width: '100%', padding: '8px 12px', fontSize: 13,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>
            )}

            {task.name === 'AddDocument' && (
              <div>
                <div style={{
                  padding: 12, backgroundColor: '#f0f9ff', border: '1px solid #bae6fd',
                  borderRadius: 6, fontSize: 13, color: '#0369a1', lineHeight: 1.5,
                }}>
                  The document for this task is selected in the <strong>Input</strong> sub-tab.
                  Choose "Select a Document" to pick a specific document, or "Step Input"
                  to use text from the previous step.
                </div>
              </div>
            )}

            {task.name === 'DescribeImage' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Image URL
                  </label>
                  <input
                    type="text"
                    value={getTextValue('image_url')}
                    onChange={e => setTextValue('image_url', e.target.value)}
                    placeholder="https://example.com/image.png"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Description Prompt
                  </label>
                  <textarea
                    value={getTextValue('prompt')}
                    onChange={e => setTextValue('prompt', e.target.value)}
                    placeholder="Describe this image in detail."
                    rows={4}
                    style={{
                      width: '100%', padding: '10px 12px', fontSize: 14,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'CodeNode' && (
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Python Code
                </label>
                <textarea
                  value={getTextValue('code')}
                  onChange={e => setTextValue('code', e.target.value)}
                  placeholder={'# Input data is available as `data`\n# Set `result` to your output\n\nresult = str(data).upper()'}
                  rows={12}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 13,
                    fontFamily: 'monospace', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                  }}
                />
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
                  The input from the previous step is available as <code style={{ backgroundColor: '#f3f4f6', padding: '1px 4px', borderRadius: 3 }}>data</code>.
                  Set the <code style={{ backgroundColor: '#f3f4f6', padding: '1px 4px', borderRadius: 3 }}>result</code> variable to produce output.
                  Available modules: json, re, math, datetime.
                </div>
              </div>
            )}

            {task.name === 'CrawlerNode' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Starting URL
                  </label>
                  <input
                    type="text"
                    value={getTextValue('start_url')}
                    onChange={e => setTextValue('start_url', e.target.value)}
                    placeholder="https://example.com"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Max Pages
                  </label>
                  <input
                    type="number"
                    value={getTextValue('max_pages') || '5'}
                    onChange={e => setTextValue('max_pages', e.target.value)}
                    min={1}
                    max={50}
                    style={{
                      width: 100, padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Allowed Domains
                  </label>
                  <input
                    type="text"
                    value={getTextValue('allowed_domains')}
                    onChange={e => setTextValue('allowed_domains', e.target.value)}
                    placeholder="example.com, docs.example.com"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                    Comma-separated list. Defaults to the starting URL's domain.
                  </div>
                </div>
              </div>
            )}

            {task.name === 'ResearchNode' && (
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Research Question / Topic
                </label>
                <textarea
                  value={getTextValue('question')}
                  onChange={e => setTextValue('question', e.target.value)}
                  placeholder="e.g., What are the main themes and conclusions in this data?"
                  rows={6}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 14,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                  }}
                />
              </div>
            )}

            {task.name === 'KnowledgeBaseQuery' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                    Knowledge Base
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      value={getTextValue('kb_uuid')}
                      onChange={e => setTextValue('kb_uuid', e.target.value)}
                      style={{
                        width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                        border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                        color: getTextValue('kb_uuid') ? '#374151' : '#9ca3af',
                        appearance: 'none', paddingRight: 32,
                      }}
                    >
                      <option value="">Select a knowledge base…</option>
                      {knowledgeBases.map(kb => (
                        <option key={kb.uuid} value={kb.uuid}>
                          {kb.title}{kb.status !== 'ready' ? ` (${kb.status})` : ''}
                        </option>
                      ))}
                    </select>
                    <ChevronDown style={{
                      position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                      width: 14, height: 14, color: '#9ca3af', pointerEvents: 'none',
                    }} />
                  </div>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                    Search Query
                  </label>
                  <textarea
                    value={getTextValue('query')}
                    onChange={e => setTextValue('query', e.target.value)}
                    placeholder="e.g., What are the eligibility requirements?"
                    rows={3}
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                    }}
                  />
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                    The top matching chunks are returned as text and passed to the next step.
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                    Results to retrieve
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={getTextValue('k') || '8'}
                    onChange={e => setTextValue('k', e.target.value)}
                    style={{
                      width: 80, padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'APINode' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    URL
                  </label>
                  <input
                    type="text"
                    value={getTextValue('url')}
                    onChange={e => setTextValue('url', e.target.value)}
                    placeholder="https://api.example.com/endpoint"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    HTTP Method
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      value={getTextValue('method') || 'GET'}
                      onChange={e => setTextValue('method', e.target.value)}
                      style={{
                        width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                        border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                        color: '#374151', appearance: 'none', paddingRight: 32,
                      }}
                    >
                      <option value="GET">GET</option>
                      <option value="POST">POST</option>
                      <option value="PUT">PUT</option>
                      <option value="DELETE">DELETE</option>
                    </select>
                    <ChevronDown style={{
                      position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                      width: 14, height: 14, color: '#9ca3af', pointerEvents: 'none',
                    }} />
                  </div>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Headers (JSON)
                  </label>
                  <textarea
                    value={getTextValue('headers')}
                    onChange={e => setTextValue('headers', e.target.value)}
                    placeholder={'{"Authorization": "Bearer ...", "Content-Type": "application/json"}'}
                    rows={3}
                    style={{
                      width: '100%', padding: '10px 12px', fontSize: 13,
                      fontFamily: 'monospace', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Request Body
                  </label>
                  <textarea
                    value={getTextValue('body')}
                    onChange={e => setTextValue('body', e.target.value)}
                    placeholder={'{"key": "value"}'}
                    rows={4}
                    style={{
                      width: '100%', padding: '10px 12px', fontSize: 13,
                      fontFamily: 'monospace', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'DocumentRenderer' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Output Format
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      value={getTextValue('format') || 'md'}
                      onChange={e => setTextValue('format', e.target.value)}
                      style={{
                        width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                        border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                        color: '#374151', appearance: 'none', paddingRight: 32,
                      }}
                    >
                      <option value="md">Markdown (.md)</option>
                      <option value="txt">Plain Text (.txt)</option>
                    </select>
                    <ChevronDown style={{
                      position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                      width: 14, height: 14, color: '#9ca3af', pointerEvents: 'none',
                    }} />
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Filename
                  </label>
                  <input
                    type="text"
                    value={getTextValue('filename') || 'output'}
                    onChange={e => setTextValue('filename', e.target.value)}
                    placeholder="output"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'FormFiller' && (
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Template
                </label>
                <textarea
                  value={getTextValue('template')}
                  onChange={e => setTextValue('template', e.target.value)}
                  placeholder={'Dear {{name}},\n\nThank you for your {{item}}.\n\nBest regards,\n{{sender}}'}
                  rows={10}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 14,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.5,
                  }}
                />
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
                  Use <code style={{ backgroundColor: '#f3f4f6', padding: '1px 4px', borderRadius: 3 }}>{'{{placeholder}}'}</code> syntax.
                  AI will fill placeholders from the input data.
                </div>
              </div>
            )}

            {task.name === 'DataExport' && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Export Format
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      value={getTextValue('format') || 'json'}
                      onChange={e => setTextValue('format', e.target.value)}
                      style={{
                        width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                        border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
                        color: '#374151', appearance: 'none', paddingRight: 32,
                      }}
                    >
                      <option value="json">JSON (.json)</option>
                      <option value="csv">CSV (.csv)</option>
                    </select>
                    <ChevronDown style={{
                      position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                      width: 14, height: 14, color: '#9ca3af', pointerEvents: 'none',
                    }} />
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                    Filename
                  </label>
                  <input
                    type="text"
                    value={getTextValue('filename') || 'export'}
                    onChange={e => setTextValue('filename', e.target.value)}
                    placeholder="export"
                    style={{
                      width: '100%', padding: '8px 12px', fontSize: 13,
                      fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            )}

            {task.name === 'PackageBuilder' && (
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Package Name
                </label>
                <input
                  type="text"
                  value={getTextValue('package_name') || 'package'}
                  onChange={e => setTextValue('package_name', e.target.value)}
                  placeholder="package"
                  style={{
                    width: '100%', padding: '8px 12px', fontSize: 13,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 6 }}>
                  Creates a .zip containing output.json and output.txt from the input data.
                </div>
              </div>
            )}

            {/* Model override for LLM tasks */}
            {LLM_TASKS.includes(task.name) && models.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                  Model Override <span style={{ fontWeight: 400, color: '#9ca3af' }}>(optional)</span>
                </label>
                <select
                  value={(taskData.model as string) || ''}
                  onChange={e => setTaskData(prev => ({ ...prev, model: e.target.value }))}
                  style={{
                    width: '100%', padding: '8px 12px', fontSize: 13, borderRadius: 6,
                    border: '1px solid #d1d5db', background: '#fff', color: '#374151',
                  }}
                >
                  <option value="">Use workflow default</option>
                  {models.map(m => {
                    const hints = [m.speed, m.tier ? `${m.tier} tier` : ''].filter(Boolean).join(', ')
                    const label = (m.tag || m.name) + (m.external ? ' (External)' : '') + (hints ? ` — ${hints}` : '')
                    return <option key={m.name} value={m.name}>{label}</option>
                  })}
                </select>
              </div>
            )}

            {/* Test result display */}
            {testResult !== null && (
              <div style={{ marginTop: 16 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
                  fontSize: 13, color: '#16a34a', fontWeight: 600,
                }}>
                  <CheckCircle style={{ width: 14, height: 14 }} />
                  Test Completed
                </div>
                <div style={{
                  backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
                  padding: 12, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
                  maxHeight: 200, overflowY: 'auto', color: '#374151',
                }}>
                  {typeof testResult === 'string' ? testResult : JSON.stringify(testResult, null, 2)}
                </div>
              </div>
            )}

            {testError && (
              <div style={{ marginTop: 16 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 13, color: '#dc2626', fontWeight: 600,
                }}>
                  <XCircle style={{ width: 14, height: 14 }} />
                  {testError}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ===== INPUT SUB-TAB ===== */}
        {subTab === 'input' && (
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>
              Data Source
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Step Input */}
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: 12,
                border: inputSource === 'step_input' ? '2px solid var(--highlight-color, #eab308)' : '1px solid #e5e7eb',
                borderRadius: 8, cursor: 'pointer', backgroundColor: '#fff',
              }}>
                <input
                  type="radio"
                  name="input_source"
                  checked={inputSource === 'step_input'}
                  onChange={() => setInputSource('step_input')}
                  style={{ marginTop: 2 }}
                />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Step Input</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    Use the output from the previous step as input for this task.
                  </div>
                </div>
              </label>

              {/* Select a Document */}
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: 12,
                border: inputSource === 'select_document' ? '2px solid var(--highlight-color, #eab308)' : '1px solid #e5e7eb',
                borderRadius: 8, cursor: 'pointer', backgroundColor: '#fff',
              }}>
                <input
                  type="radio"
                  name="input_source"
                  checked={inputSource === 'select_document'}
                  onChange={() => setInputSource('select_document')}
                  style={{ marginTop: 2 }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Select a Document</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    Choose a specific document to use as input.
                  </div>
                  {inputSource === 'select_document' && (
                    <div style={{ marginTop: 8, position: 'relative' }}>
                      <input
                        type="text"
                        value={docSearchQuery}
                        onChange={e => setDocSearchQuery(e.target.value)}
                        placeholder="Search documents..."
                        style={{
                          width: '100%', padding: '8px 12px', fontSize: 13,
                          fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                          outline: 'none', boxSizing: 'border-box',
                        }}
                        onFocus={() => docSearchResults.length > 0 && setShowDocDropdown(true)}
                        onBlur={() => setTimeout(() => setShowDocDropdown(false), 200)}
                      />
                      {showDocDropdown && docSearchResults.length > 0 && (
                        <div style={{
                          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                          backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
                          boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10,
                          maxHeight: 200, overflowY: 'auto',
                        }}>
                          {docSearchResults.map(doc => (
                            <div
                              key={doc.uuid}
                              onMouseDown={() => {
                                setSelectedDocUuid(doc.uuid)
                                setDocSearchQuery(doc.title)
                                setShowDocDropdown(false)
                              }}
                              style={{
                                padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: 8,
                                backgroundColor: doc.uuid === selectedDocUuid ? '#f3f4f6' : '#fff',
                              }}
                              onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                              onMouseLeave={e => { e.currentTarget.style.backgroundColor = doc.uuid === selectedDocUuid ? '#f3f4f6' : '#fff' }}
                            >
                              <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {doc.title}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                      {selectedDocUuid && !showDocDropdown && (
                        <div style={{
                          marginTop: 6, display: 'flex', alignItems: 'center', gap: 6,
                          padding: '6px 10px', backgroundColor: '#f3f4f6', borderRadius: 6, fontSize: 12,
                        }}>
                          <FileText style={{ width: 12, height: 12, color: '#6b7280' }} />
                          <span style={{ color: '#374151', flex: 1 }}>{docSearchQuery || selectedDocUuid}</span>
                          <button
                            onClick={() => { setSelectedDocUuid(''); setDocSearchQuery('') }}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#9ca3af', display: 'flex' }}
                          >
                            <X style={{ width: 12, height: 12 }} />
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </label>

              {/* Workflow Documents */}
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: 12,
                border: inputSource === 'workflow_documents' ? '2px solid var(--highlight-color, #eab308)' : '1px solid #e5e7eb',
                borderRadius: 8, cursor: 'pointer', backgroundColor: '#fff',
              }}>
                <input
                  type="radio"
                  name="input_source"
                  checked={inputSource === 'workflow_documents'}
                  onChange={() => setInputSource('workflow_documents')}
                  style={{ marginTop: 2 }}
                />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Workflow Documents</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    Use the documents selected when the workflow runs, plus any fixed documents.
                  </div>
                </div>
              </label>
            </div>
          </div>
        )}

        {/* ===== OUTPUT SUB-TAB ===== */}
        {subTab === 'output' && (
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>
              Post-Processing
            </div>
            <label style={{
              display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 12,
            }}>
              <input
                type="checkbox"
                checked={postProcessEnabled}
                onChange={e => setPostProcessEnabled(e.target.checked)}
              />
              <span style={{ fontSize: 13, color: '#374151' }}>Post-process output with a prompt</span>
            </label>

            {postProcessEnabled && (
              <div>
                <div style={{
                  padding: '8px 12px', backgroundColor: '#f0f9ff', border: '1px solid #bae6fd',
                  borderRadius: 6, fontSize: 12, color: '#0369a1', marginBottom: 12, lineHeight: 1.5,
                }}>
                  This prompt will be applied to the task's output before it passes to the next step.
                </div>
                <textarea
                  value={postProcessPrompt}
                  onChange={e => setPostProcessPrompt(e.target.value)}
                  placeholder="e.g., Summarize the extracted data into bullet points"
                  rows={6}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 13,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                    lineHeight: 1.5,
                  }}
                />
              </div>
            )}

            {!postProcessEnabled && (
              <div style={{
                padding: 16, backgroundColor: '#fafafa', border: '1px solid #e5e7eb',
                borderRadius: 8, fontSize: 13, color: '#6b7280', textAlign: 'center',
              }}>
                Output will pass directly to the next step without modification.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Test progress bar */}
      {testing && (
        <div style={{
          padding: '12px 20px', borderTop: '1px solid #e5e7eb', backgroundColor: '#fafafa',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Loader2 style={{ width: 14, height: 14, color: 'var(--highlight-color, #eab308)', animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: 13, fontWeight: 500, color: '#374151' }}>{testMessage}</span>
          </div>
          <div style={{
            height: 4, borderRadius: 2, backgroundColor: '#e5e7eb', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', borderRadius: 2,
              backgroundColor: 'var(--highlight-color, #eab308)',
              width: `${testProgress}%`,
              transition: 'width 0.5s ease',
            }} />
          </div>
        </div>
      )}

      {/* Bottom toolbar */}
      <div style={{
        padding: '12px 20px', borderTop: '1px solid #e5e7eb', flexShrink: 0,
        display: 'flex', gap: 8,
      }}>
        <button
          onClick={handleTestStep}
          disabled={testing || selectedDocUuids.length === 0}
          style={{
            flex: 1, padding: '10px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
            border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
            cursor: testing || selectedDocUuids.length === 0 ? 'not-allowed' : 'pointer',
            color: '#374151',
            opacity: testing || selectedDocUuids.length === 0 ? 0.5 : 1,
          }}
        >
          {testing ? 'Testing...' : 'Test Step'}
        </button>
        <button
          onClick={handleUpdate}
          disabled={saving}
          style={{
            flex: 1, padding: '10px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
            border: 'none', borderRadius: 6,
            backgroundColor: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            cursor: saving ? 'not-allowed' : 'pointer',
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Updating...' : 'Update'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Workflow output card (shown in design canvas during/after run)
// ---------------------------------------------------------------------------

function WorkflowOutputCard({ status, sessionId, running, runElapsed, showDownloadPopup, setShowDownloadPopup }: {
  status: WorkflowStatus | null
  sessionId: string | null
  running: boolean
  runElapsed: number
  showDownloadPopup: boolean
  setShowDownloadPopup: (v: boolean) => void
}) {
  const isCompleted = status?.status === 'completed'
  const isError = status?.status === 'error' || status?.status === 'failed'
  const isDone = isCompleted || isError

  const finalOutput = status?.final_output as Record<string, unknown> | null
  const output = finalOutput?.output ?? finalOutput

  const renderOutput = (data: unknown): string => {
    if (data === null || data === undefined) return ''
    let md: string
    if (typeof data === 'string') {
      md = data
    } else {
      try { md = '```json\n' + JSON.stringify(data, null, 2) + '\n```' } catch { md = String(data) }
    }
    return DOMPurify.sanitize(marked.parse(md) as string)
  }

  return (
    <div style={{
      backgroundColor: '#fff', borderRadius: 'var(--ui-radius, 8px)',
      boxShadow: '0 6px 18px rgba(0,0,0,0.05)', padding: 20,
      border: isDone
        ? (isError ? '2px solid #fca5a5' : '2px solid #86efac')
        : '2px solid #e5e7eb',
    }}>
      <div style={{ fontWeight: 600, fontSize: 14, color: '#202124', marginBottom: 8 }}>
        {running ? 'Workflow Running' : isCompleted ? 'Output' : isError ? 'Error' : 'View Output'}
      </div>

      {/* Running state */}
      {running && (
        <div>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
            {status?.current_step_name || 'Preparing...'}
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af' }}>
            {runElapsed}s elapsed
            {status && status.num_steps_total > 0 && (
              <> &mdash; Step {status.num_steps_completed + 1} of {status.num_steps_total}</>
            )}
          </div>
          <div style={{
            marginTop: 8, height: 4, borderRadius: 2,
            backgroundColor: '#e5e7eb', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', borderRadius: 2,
              backgroundColor: 'var(--highlight-color, #eab308)',
              width: status && status.num_steps_total > 0
                ? `${(status.num_steps_completed / status.num_steps_total) * 100}%`
                : '10%',
              transition: 'width 0.3s',
              backgroundImage: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
              backgroundSize: '200% 100%',
              animation: 'shimmer 1.5s infinite',
            }} />
          </div>
        </div>
      )}

      {/* Completed */}
      {isCompleted && (
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
            fontSize: 13, color: '#16a34a', fontWeight: 500,
          }}>
            <CheckCircle style={{ width: 16, height: 16 }} />
            Completed
          </div>
          <div
            style={{
              backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
              padding: 12, fontSize: 13, lineHeight: 1.6,
              maxHeight: 300, overflowY: 'auto', color: '#374151',
            }}
            dangerouslySetInnerHTML={{ __html: renderOutput(output) }}
          />
          <div style={{ marginTop: 12, position: 'relative', display: 'inline-block' }}>
            <button
              onClick={() => setShowDownloadPopup(!showDownloadPopup)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
                fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6,
                backgroundColor: '#fff', cursor: 'pointer', color: '#374151',
              }}
            >
              <Download style={{ width: 14, height: 14 }} />
              Download
            </button>
            {showDownloadPopup && sessionId && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, marginTop: 4,
                backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
                boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10, minWidth: 200,
                padding: '4px 0',
              }}>
                {([
                  { fmt: 'json', label: 'JSON', desc: 'Structured data' },
                  { fmt: 'csv', label: 'CSV', desc: 'Spreadsheet format' },
                  { fmt: 'pdf', label: 'PDF', desc: 'Printable report' },
                  { fmt: 'text', label: 'Plain Text', desc: 'Raw text output' },
                ] as const).map(({ fmt, label, desc }) => (
                  <a
                    key={fmt}
                    href={downloadResults(sessionId, fmt)}
                    onClick={() => setShowDownloadPopup(false)}
                    style={{
                      display: 'flex', flexDirection: 'column', gap: 1,
                      padding: '8px 14px', fontSize: 13, fontWeight: 500,
                      color: '#374151', textDecoration: 'none',
                      transition: 'background-color 0.1s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                    onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#fff' }}
                  >
                    <span>{label}</span>
                    <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 400 }}>{desc}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#dc2626', fontWeight: 500 }}>
          <XCircle style={{ width: 16, height: 16 }} />
          Failed
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Batch output card
// ---------------------------------------------------------------------------

function BatchOutputCard({ batchStatus, running, runElapsed }: {
  batchStatus: BatchStatus
  running: boolean
  runElapsed: number
}) {
  const isCompleted = batchStatus.status === 'completed'
  const isError = batchStatus.status === 'failed'
  const isDone = isCompleted || isError
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const renderOutput = (data: unknown): string => {
    if (data === null || data === undefined) return ''
    let md: string
    if (typeof data === 'string') {
      md = data
    } else {
      try { md = '```json\n' + JSON.stringify(data, null, 2) + '\n```' } catch { md = String(data) }
    }
    return DOMPurify.sanitize(marked.parse(md) as string)
  }

  return (
    <div style={{
      backgroundColor: '#fff', borderRadius: 'var(--ui-radius, 8px)',
      boxShadow: '0 6px 18px rgba(0,0,0,0.05)', padding: 20,
      border: isDone
        ? (isError ? '2px solid #fca5a5' : '2px solid #86efac')
        : '2px solid #e5e7eb',
    }}>
      <div style={{ fontWeight: 600, fontSize: 14, color: '#202124', marginBottom: 8 }}>
        {running ? 'Batch Running' : isCompleted ? 'Batch Complete' : isError ? 'Batch Failed' : 'Batch Output'}
      </div>

      {/* Progress summary */}
      <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>
        {batchStatus.completed} of {batchStatus.total} completed
        {batchStatus.failed > 0 && <span style={{ color: '#dc2626' }}> ({batchStatus.failed} failed)</span>}
        {running && <span> &mdash; {runElapsed}s elapsed</span>}
      </div>

      {/* Progress bar */}
      <div style={{
        height: 4, borderRadius: 2, backgroundColor: '#e5e7eb',
        overflow: 'hidden', marginBottom: 12,
      }}>
        <div style={{
          height: '100%', borderRadius: 2,
          backgroundColor: batchStatus.failed > 0 && !running ? '#fca5a5' : 'var(--highlight-color, #eab308)',
          width: batchStatus.total > 0
            ? `${((batchStatus.completed + batchStatus.failed) / batchStatus.total) * 100}%`
            : '0%',
          transition: 'width 0.3s',
        }} />
      </div>

      {/* Per-document items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {batchStatus.items.map((item, idx) => {
          const itemDone = item.status === 'completed'
          const itemFailed = item.status === 'error' || item.status === 'failed'
          const itemRunning = item.status === 'running'
          const isExpanded = expandedIdx === idx

          return (
            <div key={item.session_id} style={{
              border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden',
            }}>
              <div
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                  cursor: itemDone ? 'pointer' : 'default',
                  backgroundColor: itemDone ? '#f0fdf4' : itemFailed ? '#fef2f2' : '#fff',
                }}
              >
                {itemDone && <CheckCircle style={{ width: 14, height: 14, color: '#16a34a', flexShrink: 0 }} />}
                {itemFailed && <XCircle style={{ width: 14, height: 14, color: '#dc2626', flexShrink: 0 }} />}
                {itemRunning && <Loader2 style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0, animation: 'spin 1s linear infinite' }} />}
                {!itemDone && !itemFailed && !itemRunning && <Circle style={{ width: 14, height: 14, color: '#d1d5db', flexShrink: 0 }} />}
                <span style={{ fontSize: 13, color: '#374151', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.document_title || item.session_id}
                </span>
                {itemRunning && item.current_step_name && (
                  <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0 }}>{item.current_step_name}</span>
                )}
                {itemDone && (
                  <ChevronDown style={{
                    width: 14, height: 14, color: '#9ca3af', flexShrink: 0,
                    transition: 'transform 0.15s',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  }} />
                )}
              </div>
              {isExpanded && itemDone && item.final_output && (
                <div style={{
                  borderTop: '1px solid #e5e7eb', padding: 12,
                  backgroundColor: '#f9fafb', fontSize: 13, lineHeight: 1.6,
                  maxHeight: 200, overflowY: 'auto', color: '#374151',
                }}>
                  <div dangerouslySetInnerHTML={{
                    __html: renderOutput((item.final_output as Record<string, unknown>)?.output ?? item.final_output),
                  }} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Browser Automation task design UI
// ---------------------------------------------------------------------------

const BROWSER_ACTION_TYPES = [
  { type: 'navigate', label: 'Navigate', icon: ArrowRight, color: '#2563eb', description: 'Go to a URL' },
  { type: 'click', label: 'Click', icon: Hand, color: '#7c3aed', description: 'Click an element' },
  { type: 'fill_form', label: 'Fill Form', icon: Keyboard, color: '#16a34a', description: 'Enter text into fields' },
  { type: 'extract', label: 'Extract', icon: Download, color: '#ea580c', description: 'Extract data from page' },
  { type: 'smart_action', label: 'Smart Action', icon: Sparkles, color: '#ec4899', description: 'AI-driven action' },
  { type: 'login_pause', label: 'Login Pause', icon: Pause, color: '#ca8a04', description: 'Wait for manual login' },
  { type: 'verify', label: 'Verify', icon: ShieldCheck, color: '#0d9488', description: 'Assert a condition' },
] as const

function BrowserAutomationDesign({ taskData, setTextValue, getTextValue, setTaskData }: {
  taskData: Record<string, unknown>
  setTextValue: (key: string, value: string) => void
  getTextValue: (key: string) => string
  setTaskData: React.Dispatch<React.SetStateAction<Record<string, unknown>>>
}) {
  const [baTab, setBaTab] = useState<'record' | 'manual'>('manual')
  const actions = (taskData.actions as Array<{ type: string; config: Record<string, string> }>) || []

  const addAction = (type: string) => {
    const newActions = [...actions, { type, config: {} }]
    setTaskData(prev => ({ ...prev, actions: newActions }))
  }

  const removeAction = (idx: number) => {
    const newActions = actions.filter((_, i) => i !== idx)
    setTaskData(prev => ({ ...prev, actions: newActions }))
  }

  const updateActionConfig = (idx: number, key: string, value: string) => {
    const newActions = [...actions]
    newActions[idx] = { ...newActions[idx], config: { ...newActions[idx].config, [key]: value } }
    setTaskData(prev => ({ ...prev, actions: newActions }))
  }

  const summarizeEnabled = !!(taskData.summarization as Record<string, unknown>)?.enabled
  const summaryPrompt = ((taskData.summarization as Record<string, unknown>)?.prompt_template as string) || ''

  return (
    <div>
      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 16, borderBottom: '1px solid #e5e7eb' }}>
        {([
          { key: 'record' as const, label: 'Record Actions' },
          { key: 'manual' as const, label: 'Build Manually' },
        ]).map(t => (
          <button
            key={t.key}
            onClick={() => setBaTab(t.key)}
            style={{
              padding: '8px 16px', fontSize: 12, fontWeight: baTab === t.key ? 700 : 500,
              fontFamily: 'inherit', background: 'none', border: 'none',
              borderBottom: baTab === t.key ? '2px solid var(--highlight-color, #eab308)' : '2px solid transparent',
              color: baTab === t.key ? 'var(--highlight-color, #eab308)' : '#6b7280',
              cursor: 'pointer',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {baTab === 'record' && (
        <div>
          {/* Connection status */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: 12,
            border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 12,
          }}>
            <Circle style={{ width: 10, height: 10, fill: '#d1d5db', color: '#d1d5db' }} />
            <span style={{ fontSize: 13, color: '#6b7280' }}>Extension not connected</span>
          </div>
          <div style={{
            padding: 16, backgroundColor: '#fafafa', border: '1px solid #e5e7eb',
            borderRadius: 8, textAlign: 'center',
          }}>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
              Install the Chrome extension and connect to start recording browser actions.
            </div>
            <button
              disabled
              style={{
                padding: '8px 20px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 6, border: 'none',
                backgroundColor: '#e5e7eb', color: '#9ca3af', cursor: 'not-allowed',
              }}
            >
              Start Recording
            </button>
          </div>
        </div>
      )}

      {baTab === 'manual' && (
        <div>
          {/* Starting URL */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
              Starting URL (optional)
            </label>
            <input
              type="text"
              value={getTextValue('start_url')}
              onChange={e => setTextValue('start_url', e.target.value)}
              placeholder="https://example.com"
              style={{
                width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Allowed domains */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
              Allowed Domains (comma-separated, optional)
            </label>
            <input
              type="text"
              value={getTextValue('allowed_domains')}
              onChange={e => setTextValue('allowed_domains', e.target.value)}
              placeholder="example.com, app.example.com"
              style={{
                width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Actions list */}
          <div style={{
            fontSize: 12, fontWeight: 600, color: '#6b7280',
            textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8,
          }}>
            Actions ({actions.length})
          </div>

          {actions.map((action, idx) => {
            const def = BROWSER_ACTION_TYPES.find(a => a.type === action.type)
            const Icon = def?.icon || Globe
            return (
              <div key={idx} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: 10,
                border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 8, backgroundColor: '#fff',
              }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 6,
                  backgroundColor: (def?.color || '#6b7280') + '15',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2,
                }}>
                  <Icon style={{ width: 14, height: 14, color: def?.color || '#6b7280' }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                    {idx + 1}. {def?.label || action.type}
                  </div>
                  {(action.type === 'navigate' || action.type === 'click' || action.type === 'fill_form' || action.type === 'extract' || action.type === 'smart_action' || action.type === 'verify') && (
                    <input
                      type="text"
                      value={action.config.value || ''}
                      onChange={e => updateActionConfig(idx, 'value', e.target.value)}
                      placeholder={
                        action.type === 'navigate' ? 'URL to navigate to' :
                        action.type === 'click' ? 'CSS selector or description' :
                        action.type === 'fill_form' ? 'selector=value (e.g., #email=test@example.com)' :
                        action.type === 'extract' ? 'CSS selector or description' :
                        action.type === 'smart_action' ? 'Describe what to do in natural language' :
                        'Condition to verify'
                      }
                      style={{
                        width: '100%', padding: '6px 8px', fontSize: 12, fontFamily: 'inherit',
                        border: '1px solid #e5e7eb', borderRadius: 4, outline: 'none', boxSizing: 'border-box',
                      }}
                    />
                  )}
                </div>
                <button onClick={() => removeAction(idx)} style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex', flexShrink: 0,
                }}>
                  <Trash2 style={{ width: 13, height: 13 }} />
                </button>
              </div>
            )
          })}

          {/* Add action buttons */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {BROWSER_ACTION_TYPES.map(at => {
              const Icon = at.icon
              return (
                <button
                  key={at.type}
                  onClick={() => addAction(at.type)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px',
                    fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                    border: '1px solid #e5e7eb', borderRadius: 6, backgroundColor: '#fff',
                    cursor: 'pointer', color: '#374151',
                  }}
                >
                  <Icon style={{ width: 12, height: 12, color: at.color }} />
                  {at.label}
                </button>
              )
            })}
          </div>

          {/* AI summarization */}
          <div style={{ marginTop: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={summarizeEnabled}
                onChange={e => setTaskData(prev => ({
                  ...prev,
                  summarization: { enabled: e.target.checked, prompt_template: summaryPrompt },
                }))}
              />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Summarize results with AI</span>
            </label>
            {summarizeEnabled && (
              <textarea
                value={summaryPrompt}
                onChange={e => setTaskData(prev => ({
                  ...prev,
                  summarization: { enabled: true, prompt_template: e.target.value },
                }))}
                placeholder="Summarize the extracted data focusing on..."
                rows={2}
                style={{
                  width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                  border: '1px solid #d1d5db', borderRadius: 6, outline: 'none',
                  resize: 'vertical', boxSizing: 'border-box',
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Input Tab — trigger configuration with folder watch
// ---------------------------------------------------------------------------


function InputTab({ workflow, openWorkflowId, onRefresh }: {
  workflow: Workflow
  openWorkflowId: string | null
  onRefresh: () => void
}) {
  const [triggerType, setTriggerType] = useState(workflow.input_config?.trigger_type || 'manual')
  const [saving, setSaving] = useState(false)

  const handleTriggerChange = async (value: string) => {
    setTriggerType(value)
    if (!openWorkflowId) return
    setSaving(true)
    try {
      await updateWorkflow(openWorkflowId, { input_config: { trigger_type: value } })
      onRefresh()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 16 }}>
        Input Configuration
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Input type selector */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Input Type</div>
          <select
            value={triggerType}
            onChange={e => handleTriggerChange(e.target.value)}
            disabled={saving}
            style={{
              width: '100%', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 12px',
              backgroundColor: '#fff', color: '#374151',
            }}
          >
            <option value="manual">Manual (Select Documents)</option>
            <option value="text_input">Text Input</option>
          </select>
        </div>

        {/* Manual */}
        {triggerType === 'manual' && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fafafa',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Fixed Documents
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              Pre-assign documents that will always be included when this workflow runs.
            </div>
            <div style={{
              border: '2px dashed #d1d5db', borderRadius: 8, padding: '24px 16px',
              textAlign: 'center', color: '#9ca3af', fontSize: 13,
            }}>
              Drag documents here or click to browse
            </div>
          </div>
        )}

        {/* Text Input */}
        {triggerType === 'text_input' && (
          <>
            <div style={{
              border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fafafa',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                Text Input
              </div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                Provide text directly when running this workflow. A text area will appear in the run panel below.
                You can also select documents to include alongside the text.
              </div>
            </div>
            <div style={{
              border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fafafa',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                Fixed Documents (optional)
              </div>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
                Pre-assign documents to always include alongside the text input.
              </div>
              <div style={{
                border: '2px dashed #d1d5db', borderRadius: 8, padding: '24px 16px',
                textAlign: 'center', color: '#9ca3af', fontSize: 13,
              }}>
                Drag documents here or click to browse
              </div>
            </div>
          </>
        )}

      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Validate Tab — run validation with grade + check results
// ---------------------------------------------------------------------------

const GRADE_COLORS: Record<string, { bg: string; text: string }> = {
  A: { bg: '#dcfce7', text: '#16a34a' },
  B: { bg: '#dbeafe', text: '#2563eb' },
  C: { bg: '#fef3c7', text: '#ca8a04' },
  D: { bg: '#fed7aa', text: '#ea580c' },
  F: { bg: '#fee2e2', text: '#dc2626' },
}

const CHECK_STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  PASS: { bg: '#dcfce7', text: '#16a34a', label: 'PASS' },
  FAIL: { bg: '#fee2e2', text: '#dc2626', label: 'FAIL' },
  WARN: { bg: '#fef3c7', text: '#ca8a04', label: 'WARN' },
  SKIP: { bg: '#f3f4f6', text: '#6b7280', label: 'SKIP' },
}


function ValidateTab({ workflowId, selectedDocUuids }: { workflowId: string | null; selectedDocUuids: string[] }) {
  // Plan state
  const [planChecks, setPlanChecks] = useState<ValidationCheckDefinition[]>([])
  const [planLoading, setPlanLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Plan editing state
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [addingCheck, setAddingCheck] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newCategory, setNewCategory] = useState('content')

  // Test inputs state
  const [inputs, setInputs] = useState<ValidationInputDefinition[]>([])
  const [inputsLoading, setInputsLoading] = useState(false)
  const [showDocPicker, setShowDocPicker] = useState(false)

  // Combined run & validate state
  const [runPhase, setRunPhase] = useState<'idle' | 'running' | 'validating'>('idle')
  const [runProgress, setRunProgress] = useState('')
  const cleanupRef = useRef<(() => void) | null>(null)

  // Validation results state
  const [validating, setValidating] = useState(false)
  const [checks, setChecks] = useState<ValidationCheck[]>([])
  const [gradeInfo, setGradeInfo] = useState<{ grade: string; summary: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Quality history & suggestions
  const [qualityHistory, setQualityHistory] = useState<QualityHistoryRun[]>([])
  const [suggestions, setSuggestions] = useState<string | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)

  // Debounce timers
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputsSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const savePlan = useCallback((updatedChecks: ValidationCheckDefinition[]) => {
    setPlanChecks(updatedChecks)
    if (!workflowId) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      updateValidationPlan(workflowId, updatedChecks).catch(() => {})
    }, 800)
  }, [workflowId])

  const saveInputs = useCallback((updatedInputs: ValidationInputDefinition[]) => {
    setInputs(updatedInputs)
    if (!workflowId) return
    if (inputsSaveTimerRef.current) clearTimeout(inputsSaveTimerRef.current)
    inputsSaveTimerRef.current = setTimeout(() => {
      updateValidationInputs(workflowId, updatedInputs).catch(() => {})
    }, 800)
  }, [workflowId])

  // Load plan, inputs, and quality history on mount
  useEffect(() => {
    if (!workflowId) return
    setPlanLoading(true)
    setInputsLoading(true)
    getValidationPlan(workflowId)
      .then(r => setPlanChecks(r.checks))
      .catch(() => {})
      .finally(() => setPlanLoading(false))
    getValidationInputs(workflowId)
      .then(r => setInputs(r.inputs))
      .catch(() => {})
      .finally(() => setInputsLoading(false))
    getWorkflowQualityHistory(workflowId)
      .then(r => setQualityHistory(r.runs))
      .catch(() => {})
  }, [workflowId])

  // Cleanup SSE stream on unmount
  useEffect(() => {
    return () => { cleanupRef.current?.() }
  }, [])

  const handleGenerate = async () => {
    if (!workflowId) return
    setGenerating(true)
    setError(null)
    try {
      const res = await generateValidationPlan(workflowId)
      setPlanChecks(res.checks)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate plan')
    } finally {
      setGenerating(false)
    }
  }

  const handleValidate = async () => {
    if (!workflowId || planChecks.length === 0) return
    setValidating(true)
    setError(null)
    setSuggestions(null)
    try {
      const res = await validateWorkflow(workflowId)
      setChecks(res.checks)
      setGradeInfo({ grade: res.grade, summary: res.summary })
      getWorkflowQualityHistory(workflowId)
        .then(r => setQualityHistory(r.runs))
        .catch(() => {})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed')
    } finally {
      setValidating(false)
    }
  }

  // Combined Run & Validate flow
  const handleRunAndValidate = async () => {
    if (!workflowId || planChecks.length === 0 || inputs.length === 0) return
    setError(null)
    setSuggestions(null)
    setRunPhase('running')
    setRunProgress('Preparing inputs...')

    try {
      // Collect document UUIDs from document inputs
      const docUuids: string[] = inputs
        .filter(i => i.type === 'document' && i.document_uuid)
        .map(i => i.document_uuid!)

      // Create temp documents from text inputs
      const textInputs = inputs.filter(i => i.type === 'text' && i.text)
      if (textInputs.length > 0) {
        setRunProgress('Creating temp documents...')
        const tempResult = await createTempDocuments(
          workflowId,
          textInputs.map(i => ({ text: i.text!, label: i.label || 'Text input' })),
        )
        docUuids.push(...tempResult.document_uuids)
      }

      if (docUuids.length === 0) {
        setError('No valid inputs to run the workflow with.')
        setRunPhase('idle')
        return
      }

      // Run the workflow
      setRunProgress('Starting workflow...')
      const { session_id } = await runWorkflow(workflowId, { document_uuids: docUuids })
      bumpActivitySignal()

      // Stream status until complete
      await new Promise<void>((resolve, reject) => {
        const cleanup = streamWorkflowStatus(
          session_id,
          (status) => {
            const step = status.current_step_name || ''
            const detail = status.current_step_detail || ''
            setRunProgress(
              step
                ? `Running: ${step}${detail ? ` - ${detail}` : ''} (${status.num_steps_completed}/${status.num_steps_total})`
                : `Running... (${status.num_steps_completed}/${status.num_steps_total} steps)`
            )
            if (status.status === 'completed') {
              resolve()
            } else if (status.status === 'error' || status.status === 'failed') {
              reject(new Error('Workflow execution failed'))
            }
          },
          (err) => reject(err),
        )
        cleanupRef.current = cleanup
      })

      // Now validate
      setRunPhase('validating')
      setRunProgress('Evaluating output...')
      const res = await validateWorkflow(workflowId)
      setChecks(res.checks)
      setGradeInfo({ grade: res.grade, summary: res.summary })
      getWorkflowQualityHistory(workflowId)
        .then(r => setQualityHistory(r.runs))
        .catch(() => {})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run & Validate failed')
    } finally {
      setRunPhase('idle')
      setRunProgress('')
      cleanupRef.current = null
    }
  }

  const handleGetSuggestions = async () => {
    if (!workflowId) return
    setLoadingSuggestions(true)
    try {
      const res = await getWorkflowImprovementSuggestions(workflowId)
      setSuggestions(res.suggestions)
    } catch {
      setSuggestions('Failed to generate suggestions. Please try again.')
    } finally {
      setLoadingSuggestions(false)
    }
  }

  // Test inputs handlers
  const addDocuments = (docs: { uuid: string; title: string }[]) => {
    const newInputs: ValidationInputDefinition[] = docs.map(d => ({
      id: crypto.randomUUID?.() || Math.random().toString(36).slice(2),
      type: 'document' as const,
      document_uuid: d.uuid,
      document_title: d.title,
    }))
    saveInputs([...inputs, ...newInputs])
  }

  const addTextInput = () => {
    const newInput: ValidationInputDefinition = {
      id: crypto.randomUUID?.() || Math.random().toString(36).slice(2),
      type: 'text',
      text: '',
      label: '',
    }
    saveInputs([...inputs, newInput])
  }

  const addCurrentDocuments = async () => {
    if (selectedDocUuids.length === 0) return
    const existingUuids = new Set(inputs.filter(i => i.document_uuid).map(i => i.document_uuid!))
    const newUuids = selectedDocUuids.filter(u => !existingUuids.has(u))
    if (newUuids.length === 0) return

    // Look up titles via search
    let titleMap: Record<string, string> = {}
    try {
      const res = await searchDocuments('', 100)
      for (const doc of res.items) {
        titleMap[doc.uuid] = doc.title
      }
    } catch { /* use fallback titles */ }

    const newInputs: ValidationInputDefinition[] = newUuids.map(uuid => ({
      id: crypto.randomUUID?.() || Math.random().toString(36).slice(2),
      type: 'document' as const,
      document_uuid: uuid,
      document_title: titleMap[uuid] || `Document ${uuid.slice(0, 8)}...`,
    }))
    saveInputs([...inputs, ...newInputs])
  }

  const updateTextInput = (id: string, field: 'text' | 'label', value: string) => {
    const updated = inputs.map(i => i.id === id ? { ...i, [field]: value } : i)
    saveInputs(updated)
  }

  const removeInput = (id: string) => {
    saveInputs(inputs.filter(i => i.id !== id))
  }

  // Plan editing handlers
  const handleStartEdit = (idx: number) => {
    setEditingIdx(idx)
    setEditName(planChecks[idx].name)
    setEditDesc(planChecks[idx].description)
  }

  const handleSaveEdit = (idx: number) => {
    const updated = [...planChecks]
    updated[idx] = { ...updated[idx], name: editName, description: editDesc }
    setEditingIdx(null)
    savePlan(updated)
  }

  const handleDeletePlanCheck = (idx: number) => {
    const updated = planChecks.filter((_, i) => i !== idx)
    if (editingIdx === idx) setEditingIdx(null)
    else if (editingIdx !== null && editingIdx > idx) setEditingIdx(editingIdx - 1)
    savePlan(updated)
  }

  const handleAddPlanCheck = () => {
    if (!newName.trim()) return
    const id = crypto.randomUUID?.() || Math.random().toString(36).slice(2)
    const updated = [...planChecks, { id, name: newName.trim(), description: newDesc.trim(), category: newCategory }]
    setNewName('')
    setNewDesc('')
    setNewCategory('content')
    setAddingCheck(false)
    savePlan(updated)
  }

  const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
    completeness: { bg: '#dbeafe', text: '#2563eb' },
    formatting: { bg: '#fae8ff', text: '#a21caf' },
    content: { bg: '#dcfce7', text: '#16a34a' },
    accuracy: { bg: '#fef3c7', text: '#ca8a04' },
  }

  const gradeStyle = gradeInfo ? GRADE_COLORS[gradeInfo.grade] || GRADE_COLORS.F : null
  const hasInputs = inputs.length > 0
  const hasChecks = planChecks.length > 0
  const isBusy = runPhase !== 'idle' || validating

  return (
    <div style={{ padding: 24 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 16 }}>
        Output Quality Validation
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* ---- Test Inputs Section ---- */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fafafa',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Test Inputs</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Documents or text blocks to run the workflow against during validation.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {selectedDocUuids.length > 0 && (
                <button
                  onClick={addCurrentDocuments}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                    borderRadius: 5, border: '1px solid #d1d5db', backgroundColor: '#fff',
                    color: '#374151', cursor: 'pointer',
                  }}
                >
                  <Plus style={{ width: 11, height: 11 }} /> Add Current Doc
                </button>
              )}
              <button
                onClick={() => setShowDocPicker(true)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                  borderRadius: 5, border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#374151', cursor: 'pointer',
                }}
              >
                <FileText style={{ width: 11, height: 11 }} /> Add Document
              </button>
              <button
                onClick={addTextInput}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                  borderRadius: 5, border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#374151', cursor: 'pointer',
                }}
              >
                <Type style={{ width: 11, height: 11 }} /> Add Text
              </button>
            </div>
          </div>

          {inputsLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, justifyContent: 'center' }}>
              <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', color: '#6b7280' }} />
              <span style={{ fontSize: 12, color: '#6b7280' }}>Loading inputs...</span>
            </div>
          ) : inputs.length === 0 ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
              padding: '16px', border: '2px dashed #e5e7eb', borderRadius: 8, marginTop: 4,
            }}>
              <div style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center' }}>
                No test inputs yet. Add documents or text blocks, then use "Run & Validate" to test.
              </div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>
                Without inputs, validation evaluates the last execution's output.
              </div>
            </div>
          ) : (
            <div style={{
              border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden', marginTop: 4,
              backgroundColor: '#fff',
            }}>
              {inputs.map((input, idx) => (
                <div
                  key={input.id}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px',
                    borderBottom: idx < inputs.length - 1 ? '1px solid #f3f4f6' : 'none',
                  }}
                >
                  {/* Type badge */}
                  <span style={{
                    padding: '1px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700,
                    letterSpacing: '0.05em', textTransform: 'uppercase',
                    backgroundColor: input.type === 'document' ? '#dbeafe' : '#f3e8ff',
                    color: input.type === 'document' ? '#2563eb' : '#7c3aed',
                    whiteSpace: 'nowrap', marginTop: 3,
                  }}>
                    {input.type === 'document' ? 'DOC' : 'TEXT'}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {input.type === 'document' ? (
                      <div style={{ fontSize: 13, fontWeight: 500, color: '#202124', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <FileText style={{ width: 13, height: 13, color: '#6b7280', flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {input.document_title || input.document_uuid}
                        </span>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <input
                          value={input.label || ''}
                          onChange={e => updateTextInput(input.id, 'label', e.target.value)}
                          placeholder="Label (optional)..."
                          style={{
                            fontSize: 12, fontWeight: 500, color: '#202124',
                            border: '1px solid #e5e7eb', borderRadius: 4, padding: '3px 8px',
                            fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box',
                          }}
                        />
                        <textarea
                          value={input.text || ''}
                          onChange={e => updateTextInput(input.id, 'text', e.target.value)}
                          placeholder="Paste or type test content..."
                          style={{
                            fontSize: 12, color: '#374151',
                            border: '1px solid #e5e7eb', borderRadius: 4, padding: '6px 8px',
                            fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box',
                            resize: 'vertical', minHeight: 60,
                          }}
                        />
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => removeInput(input.id)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex', flexShrink: 0 }}
                    title="Remove input"
                  >
                    <Trash2 style={{ width: 13, height: 13 }} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ---- Validation Plan Section ---- */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fafafa',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Validation Plan</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Quality checks evaluated against the workflow's actual output.
              </div>
            </div>
            {planChecks.length > 0 && (
              <button
                onClick={handleGenerate}
                disabled={generating}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                  borderRadius: 5, border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#6b7280', cursor: generating ? 'not-allowed' : 'pointer',
                  opacity: generating ? 0.6 : 1,
                }}
              >
                <RefreshCw style={{ width: 11, height: 11 }} /> Regenerate
              </button>
            )}
          </div>

          {planLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, justifyContent: 'center' }}>
              <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', color: '#6b7280' }} />
              <span style={{ fontSize: 12, color: '#6b7280' }}>Loading plan...</span>
            </div>
          ) : planChecks.length === 0 && !generating ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
              padding: '24px 16px', border: '2px dashed #d1d5db', borderRadius: 8, marginTop: 8,
            }}>
              <ShieldCheck style={{ width: 28, height: 28, color: '#9ca3af' }} />
              <div style={{ fontSize: 13, color: '#6b7280', textAlign: 'center' }}>
                No validation plan yet. Generate one from your workflow structure.
              </div>
              <button
                onClick={handleGenerate}
                disabled={generating}
                style={{
                  padding: '8px 20px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                  border: 'none', borderRadius: 6, cursor: 'pointer',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <Sparkles style={{ width: 14, height: 14 }} /> Generate Plan
              </button>
            </div>
          ) : generating ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, justifyContent: 'center' }}>
              <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', color: '#6b7280' }} />
              <span style={{ fontSize: 12, color: '#6b7280' }}>Generating quality checks...</span>
            </div>
          ) : (
            /* Editable check list */
            <div style={{
              border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden', marginTop: 8,
              backgroundColor: '#fff',
            }}>
              {planChecks.map((check, idx) => {
                const catColor = CATEGORY_COLORS[check.category || 'content'] || CATEGORY_COLORS.content
                const isEditing = editingIdx === idx
                return (
                  <div
                    key={check.id}
                    style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px',
                      borderBottom: idx < planChecks.length - 1 ? '1px solid #f3f4f6' : 'none',
                    }}
                  >
                    {/* Category badge */}
                    <span style={{
                      padding: '1px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700,
                      letterSpacing: '0.05em', textTransform: 'uppercase',
                      backgroundColor: catColor.bg, color: catColor.text,
                      whiteSpace: 'nowrap', marginTop: 3,
                    }}>
                      {check.category || 'content'}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {isEditing ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          <input
                            value={editName}
                            onChange={e => setEditName(e.target.value)}
                            style={{
                              fontSize: 13, fontWeight: 500, color: '#202124',
                              border: '1px solid #d1d5db', borderRadius: 4, padding: '4px 8px',
                              fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box',
                            }}
                            onKeyDown={e => { if (e.key === 'Enter') handleSaveEdit(idx) }}
                          />
                          <textarea
                            value={editDesc}
                            onChange={e => setEditDesc(e.target.value)}
                            placeholder="What should the evaluator look for..."
                            style={{
                              fontSize: 11, color: '#6b7280',
                              border: '1px solid #d1d5db', borderRadius: 4, padding: '4px 8px',
                              fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box',
                              resize: 'vertical', minHeight: 40,
                            }}
                          />
                        </div>
                      ) : (
                        <>
                          <div style={{ fontSize: 13, fontWeight: 500, color: '#202124' }}>{check.name}</div>
                          {check.description && (
                            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{check.description}</div>
                          )}
                        </>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      {isEditing ? (
                        <button
                          onClick={() => handleSaveEdit(idx)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#16a34a', display: 'flex' }}
                          title="Save"
                        >
                          <CheckCircle style={{ width: 14, height: 14 }} />
                        </button>
                      ) : (
                        <button
                          onClick={() => handleStartEdit(idx)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                          title="Edit check"
                        >
                          <Pencil style={{ width: 13, height: 13 }} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDeletePlanCheck(idx)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                        title="Remove check"
                      >
                        <X style={{ width: 14, height: 14 }} />
                      </button>
                    </div>
                  </div>
                )
              })}

              {/* Add check row */}
              {addingCheck ? (
                <div style={{ padding: '10px 12px', borderTop: '1px solid #f3f4f6' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                    <select
                      value={newCategory}
                      onChange={e => setNewCategory(e.target.value)}
                      style={{
                        padding: '4px 6px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                        border: '1px solid #d1d5db', cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >
                      <option value="completeness">completeness</option>
                      <option value="formatting">formatting</option>
                      <option value="content">content</option>
                      <option value="accuracy">accuracy</option>
                    </select>
                    <input
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      placeholder="Check name..."
                      autoFocus
                      style={{
                        flex: 1, fontSize: 13, border: '1px solid #d1d5db', borderRadius: 4,
                        padding: '4px 8px', fontFamily: 'inherit', outline: 'none',
                      }}
                      onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) handleAddPlanCheck() }}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      value={newDesc}
                      onChange={e => setNewDesc(e.target.value)}
                      placeholder="Description: what should the evaluator look for..."
                      style={{
                        flex: 1, fontSize: 12, border: '1px solid #d1d5db', borderRadius: 4,
                        padding: '4px 8px', fontFamily: 'inherit', outline: 'none',
                      }}
                      onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) handleAddPlanCheck() }}
                    />
                    <button
                      onClick={handleAddPlanCheck}
                      disabled={!newName.trim()}
                      style={{
                        padding: '4px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                        border: 'none', borderRadius: 4, cursor: newName.trim() ? 'pointer' : 'not-allowed',
                        backgroundColor: '#16a34a', color: '#fff', opacity: newName.trim() ? 1 : 0.5,
                      }}
                    >
                      Add
                    </button>
                    <button
                      onClick={() => { setAddingCheck(false); setNewName(''); setNewDesc(''); setNewCategory('content') }}
                      style={{
                        padding: '4px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                        border: '1px solid #d1d5db', borderRadius: 4, cursor: 'pointer',
                        backgroundColor: '#fff', color: '#374151',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setAddingCheck(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px',
                    width: '100%', background: 'none', border: 'none', borderTop: '1px solid #f3f4f6',
                    cursor: 'pointer', fontSize: 12, color: '#6b7280', fontFamily: 'inherit',
                  }}
                >
                  <Plus style={{ width: 13, height: 13 }} /> Add Check
                </button>
              )}
            </div>
          )}
        </div>

        {/* ---- Run Buttons ---- */}
        <div style={{ display: 'flex', gap: 8 }}>
          {hasInputs && hasChecks ? (
            <button
              onClick={handleRunAndValidate}
              disabled={isBusy}
              style={{
                flex: 1, padding: '10px 20px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                border: 'none', borderRadius: 6,
                cursor: isBusy ? 'not-allowed' : 'pointer',
                backgroundColor: 'var(--highlight-color, #eab308)',
                color: 'var(--highlight-text-color, #000)',
                opacity: isBusy ? 0.7 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {runPhase !== 'idle' && <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />}
              {runPhase === 'running' ? runProgress
                : runPhase === 'validating' ? 'Evaluating output...'
                : 'Run & Validate'}
            </button>
          ) : (
            <button
              onClick={handleValidate}
              disabled={isBusy || !workflowId || !hasChecks}
              style={{
                flex: 1, padding: '10px 20px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                border: 'none', borderRadius: 6,
                cursor: isBusy || !hasChecks ? 'not-allowed' : 'pointer',
                backgroundColor: 'var(--highlight-color, #eab308)',
                color: 'var(--highlight-text-color, #000)',
                opacity: isBusy || !hasChecks ? 0.5 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {validating && <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />}
              {validating ? 'Evaluating output...' : 'Run Validation'}
            </button>
          )}
        </div>
        {!hasChecks && !planLoading && !generating && (
          <div style={{ fontSize: 11, color: '#9ca3af', textAlign: 'center', marginTop: -8 }}>
            Generate or add checks to your validation plan first.
          </div>
        )}

        {error && (
          <div style={{
            padding: 12, backgroundColor: '#fee2e2', border: '1px solid #fca5a5',
            borderRadius: 8, fontSize: 13, color: '#dc2626',
          }}>
            {error}
          </div>
        )}

        {/* ---- Quality History Chart ---- */}
        {qualityHistory.length > 1 && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, backgroundColor: '#fff',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
              <TrendingUp style={{ width: 14, height: 14, color: '#6b7280' }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Quality History</span>
              <span style={{ fontSize: 11, color: '#9ca3af' }}>({qualityHistory.length} runs)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 60 }}>
              {[...qualityHistory].reverse().map((run, i) => {
                const gc = run.grade ? (GRADE_COLORS[run.grade] || GRADE_COLORS.F) : GRADE_COLORS.F
                const barHeight = Math.max(4, Math.round(run.score * 0.6))
                return (
                  <div
                    key={run.uuid}
                    title={`Run ${i + 1}: Grade ${run.grade || '?'} (Score ${Math.round(run.score)}) | ${run.checks_passed}/${run.checks_passed + run.checks_failed} passed | ${new Date(run.created_at).toLocaleDateString()}`}
                    style={{
                      flex: 1, maxWidth: 24, height: barHeight,
                      backgroundColor: gc.text, borderRadius: 2,
                      opacity: i === [...qualityHistory].length - 1 ? 1 : 0.6,
                      transition: 'height 0.2s', cursor: 'default',
                    }}
                  />
                )
              })}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
              <span style={{ fontSize: 10, color: '#9ca3af' }}>
                {new Date(qualityHistory[qualityHistory.length - 1].created_at).toLocaleDateString()}
              </span>
              <span style={{ fontSize: 10, color: '#9ca3af' }}>
                {new Date(qualityHistory[0].created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        )}

        {/* ---- Validation Results ---- */}
        {gradeInfo && (
          <>
            {/* Grade badge */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 16, padding: 16,
              border: '1px solid #e5e7eb', borderRadius: 8, backgroundColor: '#fff',
            }}>
              <div style={{
                width: 56, height: 56, borderRadius: 12,
                backgroundColor: gradeStyle?.bg,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                <span style={{ fontSize: 28, fontWeight: 800, color: gradeStyle?.text }}>
                  {gradeInfo.grade}
                </span>
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>Validation Grade</div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{gradeInfo.summary}</div>
              </div>
            </div>

            {/* Improvement Suggestions */}
            {gradeInfo.grade !== 'A' && (
              <div style={{
                border: '1px solid #fde68a', borderRadius: 8, padding: 16, backgroundColor: '#fffbeb',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: suggestions ? 12 : 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Sparkles style={{ width: 14, height: 14, color: '#d97706' }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#92400e' }}>Improvement Suggestions</span>
                  </div>
                  {!suggestions && (
                    <button
                      onClick={handleGetSuggestions}
                      disabled={loadingSuggestions}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                        borderRadius: 6, border: '1px solid #fde68a', backgroundColor: '#fff',
                        color: '#92400e', cursor: loadingSuggestions ? 'not-allowed' : 'pointer',
                        opacity: loadingSuggestions ? 0.6 : 1,
                      }}
                    >
                      {loadingSuggestions ? (
                        <><Loader2 style={{ width: 12, height: 12, animation: 'spin 1s linear infinite' }} /> Analyzing...</>
                      ) : (
                        'Get AI Suggestions'
                      )}
                    </button>
                  )}
                </div>
                {suggestions && (
                  <div style={{ fontSize: 13, color: '#78350f', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {suggestions}
                  </div>
                )}
              </div>
            )}

            {/* Check results */}
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{
                padding: '10px 16px', backgroundColor: '#f9fafb',
                borderBottom: '1px solid #e5e7eb',
                fontSize: 12, fontWeight: 600, color: '#374151',
                textTransform: 'uppercase', letterSpacing: '0.05em',
              }}>
                Check Results
              </div>
              {checks.map((check, idx) => {
                const statusStyle = CHECK_STATUS_STYLES[check.status] || CHECK_STATUS_STYLES.SKIP
                return (
                  <div
                    key={check.check_id || idx}
                    style={{
                      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 16px',
                      borderBottom: idx < checks.length - 1 ? '1px solid #f3f4f6' : 'none',
                    }}
                  >
                    <span style={{
                      padding: '2px 6px', borderRadius: 4,
                      fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
                      backgroundColor: statusStyle.bg, color: statusStyle.text,
                      whiteSpace: 'nowrap', marginTop: 2,
                    }}>
                      {check.status}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: '#202124' }}>{check.name}</div>
                      {check.detail && (
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2, lineHeight: 1.5 }}>{check.detail}</div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Document Picker Dialog */}
      {showDocPicker && (
        <DocumentPickerDialog
          onSelect={addDocuments}
          onClose={() => setShowDocPicker(false)}
          excludeUuids={inputs.filter(i => i.document_uuid).map(i => i.document_uuid!)}
        />
      )}
    </div>
  )
}
