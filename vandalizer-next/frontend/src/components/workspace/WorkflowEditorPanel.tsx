import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  X, Play, Loader2, Plus, Trash2, Pencil, SlidersHorizontal,
  FileText, Filter, Outdent, Globe, Image, Code,
  Bug, Search, Zap, Download, Package, CheckCircle, XCircle,
  MousePointerClick, PenTool, Send, ClipboardCheck, Flag,
  AlertTriangle, ChevronDown,
} from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import {
  getWorkflow, addStep, deleteStep, addTask, deleteTask, updateTask,
  updateWorkflow, updateStep, downloadResults, testStep, getTestStepStatus,
} from '../../api/workflows'
import { listSearchSets } from '../../api/extractions'
import { listContents } from '../../api/documents'
import { useWorkflowRunner } from '../../hooks/useWorkflowRunner'
import type { Workflow, WorkflowStep, WorkflowTask, WorkflowStatus, SearchSet } from '../../types/workflow'
import type { Document as VDoc } from '../../types/document'

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

type Tab = 'design' | 'input' | 'output' | 'validate'
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
  { name: 'Browser', label: 'Browser Automation', icon: Globe, color: '#2563eb', categories: ['all', 'web'], enabled: true },
  { name: 'AddDocument', label: 'Add Document', icon: FileText, color: '#6b7280', categories: ['all', 'files'], enabled: false },
  { name: 'AddWebsite', label: 'Add Website', icon: Globe, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'DescribeImage', label: 'Describe Image', icon: Image, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'CodeNode', label: 'Code Node', icon: Code, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'CrawlerNode', label: 'Crawler Node', icon: Bug, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'ResearchNode', label: 'Research Node', icon: Search, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'APINode', label: 'API Node', icon: Zap, color: '#6b7280', categories: ['all', 'web'], enabled: false },
  { name: 'DocumentRenderer', label: 'Document Renderer', icon: FileText, color: '#6b7280', categories: ['all', 'output'], enabled: false },
  { name: 'FormFiller', label: 'Form Filler', icon: MousePointerClick, color: '#6b7280', categories: ['all', 'output'], enabled: false },
  { name: 'DataExport', label: 'Data Export', icon: Download, color: '#6b7280', categories: ['all', 'output'], enabled: false },
  { name: 'PackageBuilder', label: 'Package Builder', icon: Package, color: '#6b7280', categories: ['all', 'output'], enabled: false },
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
  { key: 'output', label: 'Output', icon: Send },
  { key: 'validate', label: 'Validate', icon: ClipboardCheck },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTaskColor(name: string): string {
  if (name === 'Extraction') return '#dc2626'
  if (name === 'Prompt') return '#2563eb'
  if (name === 'Formatter' || name === 'Format') return '#16a34a'
  return '#6b7280'
}

function getTaskIcon(name: string) {
  if (name === 'Extraction') return Filter
  if (name === 'Prompt') return MousePointerClick
  if (name === 'Formatter' || name === 'Format') return Outdent
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
  const { openWorkflowId, closeWorkflow, selectedDocUuids } = useWorkspace()
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
  const [runElapsed, setRunElapsed] = useState(0)
  const runTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const newStepInputRef = useRef<HTMLInputElement>(null)

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

  const handleRun = async () => {
    if (!openWorkflowId) return
    const uuids = selectedDocUuids.length > 0 ? selectedDocUuids : []
    if (uuids.length === 0) return
    setActiveTab('design')
    await runner.start(openWorkflowId, uuids)
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
  const inputBadge = workflow.steps.some(s => s.data?.trigger_type === 'folder_watch') ? 1 : 0
  const outputBadge = workflow.steps.some(s => s.is_output) ? 1 : 0

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
          const badge = tab.key === 'input' ? inputBadge : tab.key === 'output' ? outputBadge : 0
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
            runElapsed={runElapsed}
            showDownloadPopup={showDownloadPopup}
            setShowDownloadPopup={setShowDownloadPopup}
            onClickStep={setEditingStepId}
            onAddStep={() => { setNewStepName(''); setShowNewStepModal(true) }}
          />
        )}

        {activeTab === 'input' && <InputTab />}
        {activeTab === 'output' && <OutputTab />}
        {activeTab === 'validate' && <ValidateTab />}
      </div>

      {/* ===== BOTTOM TOOLBAR (Run) ===== */}
      <div style={{ flexShrink: 0, padding: 15, backgroundColor: '#fff', boxShadow: '0 0px 23px -8px rgb(211,211,211)' }}>
        <button
          onClick={handleRun}
          disabled={runner.running || selectedDocUuids.length === 0}
          style={{
            width: '100%', padding: '12px 16px', fontSize: 14, fontWeight: 700,
            fontFamily: 'inherit', borderRadius: 'var(--ui-radius, 8px)', border: 'none',
            backgroundColor: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            cursor: runner.running || selectedDocUuids.length === 0 ? 'not-allowed' : 'pointer',
            opacity: selectedDocUuids.length === 0 && !runner.running ? 0.5 : 1,
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
  runElapsed,
  showDownloadPopup,
  setShowDownloadPopup,
  onClickStep,
  onAddStep,
}: {
  workflow: Workflow
  selectedDocCount: number
  runnerStatus: WorkflowStatus | null
  runnerRunning: boolean
  runnerSessionId: string | null
  runElapsed: number
  showDownloadPopup: boolean
  setShowDownloadPopup: (v: boolean) => void
  onClickStep: (stepId: string) => void
  onAddStep: () => void
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

      {/* Documents Selected card */}
      <div style={{
        backgroundColor: '#fff', border: '2px solid var(--highlight-color, #eab308)',
        borderRadius: 'var(--ui-radius, 8px)', padding: 15, textAlign: 'center',
        boxShadow: '0 6px 18px rgba(0,0,0,0.05)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <FileText style={{ width: 16, height: 16, color: 'var(--highlight-color, #eab308)' }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Documents Selected</span>
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
          {selectedDocCount} document{selectedDocCount !== 1 ? 's' : ''} selected
        </div>
      </div>

      {/* Step cards */}
      {workflow.steps.map((step, idx) => (
        <div key={step.id}>
          <ConnectionLine />
          <StepCard
            step={step}
            index={idx}
            isActive={runnerRunning && runnerStatus?.current_step_name === step.name}
            onClick={() => onClickStep(step.id)}
          />
        </div>
      ))}

      <ConnectionLine />

      {/* +ADD STEP */}
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

      {/* Workflow output (during/after run) */}
      {(runnerRunning || runnerStatus) && (
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

function StepCard({ step, index, isActive, onClick }: {
  step: WorkflowStep
  index: number
  isActive: boolean
  onClick: () => void
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
  onStepNameSave,
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
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: 12,
          }}>
            {filteredTypes.map(taskType => {
              const Icon = taskType.icon
              return (
                <button
                  key={taskType.name}
                  onClick={() => taskType.enabled && onSelect(taskType)}
                  disabled={!taskType.enabled}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                    padding: 16, border: '1px solid #e5e7eb',
                    borderRadius: 'var(--ui-radius, 8px)',
                    backgroundColor: '#fff',
                    cursor: taskType.enabled ? 'pointer' : 'default',
                    opacity: taskType.enabled ? 1 : 0.4,
                    fontFamily: 'inherit',
                    transition: 'box-shadow 0.15s',
                  }}
                  onMouseEnter={e => {
                    if (taskType.enabled) (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.boxShadow = 'none'
                  }}
                >
                  <div style={{
                    width: 40, height: 40, borderRadius: 8,
                    backgroundColor: taskType.enabled ? taskType.color + '15' : '#f3f4f6',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon style={{ width: 20, height: 20, color: taskType.enabled ? taskType.color : '#9ca3af' }} />
                  </div>
                  <span style={{
                    fontSize: 12, fontWeight: 600, textAlign: 'center',
                    color: taskType.enabled ? '#202124' : '#9ca3af',
                  }}>
                    {taskType.label}
                  </span>
                  {!taskType.enabled && (
                    <span style={{ fontSize: 10, color: '#9ca3af' }}>Coming soon</span>
                  )}
                </button>
              )
            })}
          </div>
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
    if (typeof data === 'string') return data
    try { return JSON.stringify(data, null, 2) } catch { return String(data) }
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
          <div style={{
            backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
            padding: 12, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
            maxHeight: 300, overflowY: 'auto', color: '#374151',
          }}>
            {renderOutput(output)}
          </div>
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
// Input Tab — trigger configuration
// ---------------------------------------------------------------------------

function InputTab() {
  const [triggerType, setTriggerType] = useState('manual')

  return (
    <div style={{ padding: 24 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 16 }}>
        Trigger Configuration
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Trigger type selector */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Trigger Type</div>
          <select
            value={triggerType}
            onChange={e => setTriggerType(e.target.value)}
            style={{
              width: '100%', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 12px',
              backgroundColor: '#fff', color: '#374151',
            }}
          >
            <option value="manual">Manual (Select Documents)</option>
            <option value="folder_watch">Folder Watch</option>
            <option value="api">API Trigger</option>
            <option value="schedule">Schedule</option>
          </select>
        </div>

        {/* Context-dependent sections */}
        {triggerType === 'manual' && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
            backgroundColor: '#fafafa',
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

        {triggerType === 'folder_watch' && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
            backgroundColor: '#fafafa',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Watch Folder
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              Automatically run the workflow when new documents are added to a folder.
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', fontStyle: 'italic' }}>
              Select a folder to watch from the file browser.
            </div>
          </div>
        )}

        {triggerType === 'api' && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
            backgroundColor: '#fafafa',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              API Endpoint
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              Trigger this workflow programmatically via the API.
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              backgroundColor: '#f3f4f6', borderRadius: 6, padding: '8px 12px',
              fontSize: 12, fontFamily: 'monospace', color: '#374151',
            }}>
              POST /api/workflows/run
            </div>
          </div>
        )}

        {triggerType === 'schedule' && (
          <div style={{
            border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
            backgroundColor: '#fafafa',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Schedule
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              Run this workflow on a recurring schedule.
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', fontStyle: 'italic' }}>
              Schedule configuration coming soon.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Output Tab — storage & delivery configuration
// ---------------------------------------------------------------------------

function OutputTab() {
  const [format, setFormat] = useState('json')
  const [savePlatform, setSavePlatform] = useState(true)
  const [exportCloud, setExportCloud] = useState(false)
  const [sendWebhook, setSendWebhook] = useState(false)
  const [emailNotify, setEmailNotify] = useState(false)

  return (
    <div style={{ padding: 24 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 16 }}>
        Output Configuration
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Output format */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Default Output Format</div>
          <select
            value={format}
            onChange={e => setFormat(e.target.value)}
            style={{
              width: '100%', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 12px',
              backgroundColor: '#fff', color: '#374151',
            }}
          >
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
            <option value="pdf">PDF Report</option>
            <option value="text">Plain Text</option>
          </select>
        </div>

        {/* Storage destinations */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fafafa',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Storage Destinations
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            Configure where workflow results are saved automatically.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={savePlatform} onChange={e => setSavePlatform(e.target.checked)} />
              <span style={{ fontSize: 13, color: '#374151' }}>Save to platform (default)</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={exportCloud} onChange={e => setExportCloud(e.target.checked)} />
              <span style={{ fontSize: 13, color: '#374151' }}>Export to cloud storage</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={sendWebhook} onChange={e => setSendWebhook(e.target.checked)} />
              <span style={{ fontSize: 13, color: '#374151' }}>Send via webhook</span>
            </label>
          </div>
        </div>

        {/* Notifications */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fafafa',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Notifications
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            Get notified when a workflow run completes or fails.
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={emailNotify} onChange={e => setEmailNotify(e.target.checked)} />
            <span style={{ fontSize: 13, color: '#374151' }}>Email notification on completion</span>
          </label>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Validate Tab — evaluation plan
// ---------------------------------------------------------------------------

function ValidateTab() {
  const [evalPlan, setEvalPlan] = useState('')

  return (
    <div style={{ padding: 24 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 16 }}>
        Validation & Evaluation
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Evaluation plan */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fafafa',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Evaluation Plan
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            Define criteria for validating workflow output quality. An AI-generated eval plan will assess
            each run against your criteria.
          </div>
          <textarea
            value={evalPlan}
            onChange={e => setEvalPlan(e.target.value)}
            placeholder="Describe what a successful workflow output looks like..."
            style={{
              width: '100%', minHeight: 100, fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '10px 12px',
              backgroundColor: '#fff', resize: 'vertical', boxSizing: 'border-box',
              color: '#374151', outline: 'none',
            }}
          />
        </div>

        {/* Test documents */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fafafa',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Test Documents
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
            Add known-good test documents with expected results to validate workflow accuracy.
          </div>
          <div style={{
            border: '2px dashed #d1d5db', borderRadius: 8, padding: '24px 16px',
            textAlign: 'center', color: '#9ca3af', fontSize: 13,
          }}>
            No test documents added yet
          </div>
        </div>

        {/* Validation history */}
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fafafa',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
            Validation History
          </div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>
            No validation runs yet. Configure an evaluation plan and test documents to begin.
          </div>
        </div>
      </div>
    </div>
  )
}
