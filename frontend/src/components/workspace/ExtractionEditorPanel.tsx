import React, { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { ExtractionTutorial } from './ExtractionTutorial'
import { X, Pencil, Loader2, Copy, Trash2, GripVertical, Plus, ChevronDown, ChevronRight, Play, TrendingUp, Sparkles, FileText, AlertTriangle, Eye, Shield, ShieldCheck, Download } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useSearchSetItems } from '../../hooks/useExtractions'
import {
  getSearchSet,
  updateSearchSet,
  cloneSearchSet,
  deleteSearchSet,
  runExtractionSync,
  buildFromDocument,
  runValidationV2,
  getExtractionQualityHistory,
  getExtractionImprovementSuggestions,
  listTestCases,
  createTestCase,
  updateTestCase,
  deleteTestCase,
  uploadPdfTemplate,
  exportExtractionPdf,
  generateExampleTemplate,
  exportSearchSetUrl,
  importSearchSet,
} from '../../api/extractions'
import type { ValidationV2Result, QualityHistoryRun, ValidationSource, TuningResult } from '../../api/extractions'
import { findBestSettings } from '../../api/extractions'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'
import { VerificationSubmitDialog } from '../shared/VerificationSubmitDialog'
import { getModels } from '../../api/config'
import type { SearchSet, ModelInfo } from '../../types/workflow'
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import { QualityBadge } from '../library/QualityBadge'
import { QualitySparkline } from '../library/QualitySparkline'
import { useQualitySparkline } from '../../hooks/useQualitySparkline'
import { getQualityStatus } from '../../api/extractions'
import type { QualityStatus } from '../../api/extractions'
import { relativeTime } from '../../utils/time'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

type Tab = 'design' | 'tools' | 'validate' | 'advanced'

interface ExtractionConfig {
  mode?: 'one_pass' | 'two_pass'
  one_pass?: { thinking?: boolean; structured?: boolean; model?: string }
  two_pass?: {
    pass1?: { thinking?: boolean; structured?: boolean; model?: string }
    pass2?: { thinking?: boolean; structured?: boolean; model?: string }
  }
  key_chunking?: { enabled?: boolean; max_keys?: number }
  repetition?: { enabled?: boolean }
}

export function ExtractionEditorPanel() {
  const { openExtractionId, openExtraction, closeExtraction, selectedDocUuids, setHighlightTerms, bumpActivitySignal } = useWorkspace()
  const [searchSet, setSearchSet] = useState<SearchSet | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('design')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [newTerm, setNewTerm] = useState('')
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<Record<string, string>>({})
  const [attachingTemplate, setAttachingTemplate] = useState(false)
  const [generatingTemplate, setGeneratingTemplate] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const templateInputRef = useRef<HTMLInputElement>(null)
  const importDefInputRef = useRef<HTMLInputElement>(null)

  const [qualityStatus, setQualityStatus] = useState<QualityStatus | null>(null)
  const [nudgeDismissed, setNudgeDismissed] = useState(false)
  const { scores: sparklineScores, refresh: refreshSparkline } = useQualitySparkline('search_set', openExtractionId ?? undefined)

  const { items, loading: itemsLoading, refresh: refreshItems, add, remove, update, reorder } =
    useSearchSetItems(openExtractionId)

  // Background refresh — does NOT set loading:true so ValidateTab state is preserved
  const refresh = useCallback(async () => {
    if (!openExtractionId) return
    try {
      const ss = await getSearchSet(openExtractionId)
      setSearchSet(ss)
    } catch {
      // silent — don't clear searchSet on refresh failure
    }
    refreshSparkline()
    getQualityStatus(openExtractionId).then(setQualityStatus).catch(() => {})
  }, [openExtractionId, refreshSparkline])

  // Initial load — shows spinner and resets design-tab results
  useEffect(() => {
    if (!openExtractionId) return
    setLoading(true)
    setResults({})
    setActiveTab('design')
    getSearchSet(openExtractionId)
      .then(setSearchSet)
      .catch(() => setSearchSet(null))
      .finally(() => setLoading(false))
    refreshSparkline()
    getQualityStatus(openExtractionId).then(setQualityStatus).catch(() => {})
  }, [openExtractionId, refreshSparkline])

  // Nudge dismissal state
  useEffect(() => {
    if (!openExtractionId) return
    const key = `quality-nudge-dismissed-${openExtractionId}`
    setNudgeDismissed(!!localStorage.getItem(key))
  }, [openExtractionId])

  // --- Title editing ---
  const startEditTitle = () => {
    setTitleDraft(searchSet?.title ?? '')
    setEditingTitle(true)
  }

  const saveTitle = async () => {
    setEditingTitle(false)
    if (!openExtractionId || titleDraft === searchSet?.title) return
    await updateSearchSet(openExtractionId, { title: titleDraft.trim() || searchSet?.title })
    refresh()
  }

  // --- Add item ---
  const handleAddItem = async () => {
    const phrase = newTerm.trim()
    if (!phrase) return
    await add(phrase)
    setNewTerm('')
  }

  // --- Run ---
  const handleRun = async () => {
    if (!openExtractionId || selectedDocUuids.length === 0) return
    setRunning(true)
    try {
      const resp = await runExtractionSync({
        search_set_uuid: openExtractionId,
        document_uuids: selectedDocUuids,
      })
      // Build key→value map from results
      const map: Record<string, string> = {}
      if (resp.results && resp.results.length > 0) {
        const first = resp.results[0]
        if (typeof first === 'object' && first !== null) {
          for (const [k, v] of Object.entries(first as Record<string, unknown>)) {
            map[k] = v === null ? 'N/A' : String(v)
          }
        }
      }
      setResults(map)
    } finally {
      setRunning(false)
      bumpActivitySignal()
    }
  }

  // --- Export ---
  const handleExport = () => {
    navigator.clipboard.writeText(JSON.stringify(results, null, 2))
  }

  // --- Tools ---
  const handleClone = async () => {
    if (!openExtractionId) return
    await cloneSearchSet(openExtractionId)
  }

  const handleDelete = async () => {
    if (!openExtractionId) return
    await deleteSearchSet(openExtractionId)
    closeExtraction()
  }

  const [buildingFromDoc, setBuildingFromDoc] = useState(false)
  const handleBuildFromDocument = async () => {
    if (!openExtractionId || selectedDocUuids.length === 0) return
    setBuildingFromDoc(true)
    try {
      await buildFromDocument(openExtractionId, selectedDocUuids)
      refreshItems()
      setActiveTab('design')
    } finally {
      setBuildingFromDoc(false)
    }
  }

  const handleAttachTemplate = async (file: File) => {
    if (!openExtractionId) return
    setAttachingTemplate(true)
    try {
      const ss = await uploadPdfTemplate(openExtractionId, file)
      setSearchSet(ss)
      refreshItems()
      setActiveTab('design')
    } finally {
      setAttachingTemplate(false)
    }
  }

  const handleGenerateTemplate = async () => {
    if (!openExtractionId) return
    setGeneratingTemplate(true)
    try {
      await generateExampleTemplate(openExtractionId)
      await refresh()
      refreshItems()
    } finally {
      setGeneratingTemplate(false)
    }
  }

  const handleExportPdf = async () => {
    if (!openExtractionId) return
    setExportingPdf(true)
    try {
      await exportExtractionPdf(openExtractionId, results, [])
    } finally {
      setExportingPdf(false)
    }
  }

  // --- Advanced config ---
  const config: ExtractionConfig = (searchSet?.extraction_config as ExtractionConfig) ?? {}

  const useDefaults = Object.keys(searchSet?.extraction_config ?? {}).length === 0

  const saveConfig = async (next: ExtractionConfig) => {
    if (!openExtractionId) return
    await updateSearchSet(openExtractionId, { extraction_config: next as Record<string, unknown> })
    refresh()
  }

  const setUseDefaults = (checked: boolean) => {
    if (checked) {
      saveConfig({} as ExtractionConfig)
    } else {
      saveConfig({ mode: 'one_pass' })
    }
  }

  // --- Render ---
  if (loading) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <PanelHeader title="Loading..." onClose={closeExtraction} />
        <div style={{ padding: 40, textAlign: 'center', color: '#888', fontSize: 13 }}>
          Loading extraction...
        </div>
      </div>
    )
  }

  if (!searchSet) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
        <PanelHeader title="Extraction" onClose={closeExtraction} />
        <div style={{ padding: 40, textAlign: 'center', color: '#d93025', fontSize: 13 }}>
          Extraction not found.
        </div>
      </div>
    )
  }

  const hasResults = Object.keys(results).length > 0

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: '#fff' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 24px 8px',
          backgroundColor: '#fff',
          flexShrink: 0,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          {editingTitle ? (
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={saveTitle}
              onKeyDown={(e) => e.key === 'Enter' && saveTitle()}
              style={{
                fontSize: 18,
                fontWeight: 600,
                color: '#202124',
                border: '1px solid #dadce0',
                borderRadius: 6,
                padding: '4px 8px',
                outline: 'none',
                width: '100%',
                fontFamily: 'inherit',
              }}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 600,
                  color: '#202124',
                  letterSpacing: '-0.01em',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {searchSet.title}
              </span>
              <button
                onClick={startEditTitle}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 4,
                  color: '#9ca3af',
                  display: 'flex',
                  flexShrink: 0,
                }}
              >
                <Pencil style={{ width: 14, height: 14 }} />
              </button>
              {searchSet.quality_tier && (
                <>
                  <QualityBadge tier={searchSet.quality_tier} score={searchSet.quality_score ?? null} />
                  {sparklineScores.length >= 2 && <QualitySparkline scores={sparklineScores} />}
                </>
              )}
              {searchSet.last_validated_at && (
                <span style={{ fontSize: 11, color: '#9ca3af', whiteSpace: 'nowrap' }}>
                  Validated {relativeTime(searchSet.last_validated_at)}
                </span>
              )}
            </div>
          )}
          <div style={{ fontSize: 12, color: '#5f6368', marginTop: 2 }}>
            {selectedDocUuids.length} document{selectedDocUuids.length !== 1 ? 's' : ''} selected
          </div>
        </div>
        <button
          onClick={closeExtraction}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 4,
            borderRadius: 4,
            color: '#5f6368',
            display: 'flex',
            flexShrink: 0,
          }}
        >
          <X style={{ width: 20, height: 20 }} />
        </button>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          borderBottom: '1px solid #e5e7eb',
          paddingLeft: 24,
          flexShrink: 0,
        }}
      >
        {(['design', 'tools', 'validate', 'advanced'] as const).map((tab) => {
          const isActive = activeTab === tab
          // Colored dot for validate tab
          let tabDot: string | null = null
          if (tab === 'validate' && qualityStatus) {
            if (qualityStatus.status === 'unvalidated') tabDot = '#9ca3af'
            else if (qualityStatus.stale) tabDot = '#eab308'
            else if (qualityStatus.score != null && qualityStatus.score < 50) tabDot = '#dc2626'
          }
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '10px 16px',
                fontSize: 13,
                fontWeight: isActive ? 600 : 400,
                fontFamily: 'inherit',
                color: isActive ? '#202124' : '#5f6368',
                background: 'none',
                border: 'none',
                borderBottom: isActive ? '2px solid #202124' : '2px solid transparent',
                cursor: 'pointer',
                textTransform: 'capitalize',
                transition: 'color 0.15s',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              {tab}
              {tabDot && (
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  backgroundColor: tabDot, display: 'inline-block',
                }} />
              )}
            </button>
          )
        })}
      </div>

      {/* Tab content — all tabs stay mounted to preserve state */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, display: activeTab === 'design' ? undefined : 'none' }}>
        <DesignTab
          items={items}
          itemsLoading={itemsLoading}
          results={results}
          hasResults={hasResults}
          running={running}
          config={config}
          docCount={selectedDocUuids.length}
          onExport={handleExport}
          onRemoveItem={remove}
          onUpdateItem={update}
          onReorder={reorder}
          searchSetUuid={openExtractionId ?? undefined}
          onHighlightValue={setHighlightTerms}
        />
      </div>
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, display: activeTab === 'tools' ? undefined : 'none' }}>
        <>
          <input
            ref={templateInputRef}
            type="file"
            accept=".pdf"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleAttachTemplate(f)
              e.target.value = ''
            }}
          />
          <input
            ref={importDefInputRef}
            type="file"
            accept=".json"
            style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0]
              if (!f) return
              e.target.value = ''
              try {
                const result = await importSearchSet(f)
                openExtraction(result.uuid)
              } catch (err: unknown) {
                alert(err instanceof Error ? err.message : 'Import failed')
              }
            }}
          />
          <ToolsTab
            onClone={handleClone}
            onDelete={handleDelete}
            onAttachTemplate={() => templateInputRef.current?.click()}
            onGenerateTemplate={handleGenerateTemplate}
            onExportPdf={handleExportPdf}
            onExportDefinition={() => window.open(exportSearchSetUrl(openExtractionId!), '_blank')}
            onImportDefinition={() => importDefInputRef.current?.click()}
            onBuildFromDocument={handleBuildFromDocument}
            buildingFromDoc={buildingFromDoc}
            attachingTemplate={attachingTemplate}
            generatingTemplate={generatingTemplate}
            exportingPdf={exportingPdf}
            hasDocuments={selectedDocUuids.length > 0}
            hasResults={Object.keys(results).length > 0}
            hasTemplate={!!searchSet?.fillable_pdf_url}
            hasItems={items.length > 0}
          />
        </>
      </div>
      {openExtractionId && (
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, display: activeTab === 'validate' ? undefined : 'none' }}>
          <ValidateTab
            searchSetUuid={openExtractionId}
            itemTitle={searchSet?.title}
            items={items}
            extractionConfig={config}
            onUpdateItem={update}
            onValidationComplete={refresh}
          />
        </div>
      )}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, display: activeTab === 'advanced' ? undefined : 'none' }}>
        <AdvancedTab
          config={config}
          useDefaults={useDefaults}
          onSetUseDefaults={setUseDefaults}
          onSaveConfig={saveConfig}
        />
      </div>

      {/* Nudge banner for unvalidated items */}
      {activeTab === 'design' && !nudgeDismissed && searchSet.validation_run_count === 0 && Object.keys(results).length > 0 && (
        <div style={{
          padding: '8px 24px', backgroundColor: '#eff6ff', borderTop: '1px solid #dbeafe',
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <Shield style={{ width: 14, height: 14, color: '#2563eb', flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: '#1e40af', flex: 1 }}>
            Check reliability with validation
          </span>
          <button
            onClick={() => setActiveTab('validate')}
            style={{
              fontSize: 12, fontWeight: 600, color: '#2563eb', background: 'none',
              border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '2px 6px',
            }}
          >
            Validate
          </button>
          <button
            onClick={() => {
              setNudgeDismissed(true)
              if (openExtractionId) localStorage.setItem(`quality-nudge-dismissed-${openExtractionId}`, '1')
            }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 2,
              color: '#9ca3af', display: 'flex',
            }}
          >
            <X style={{ width: 12, height: 12 }} />
          </button>
        </div>
      )}

      {/* Bottom toolbar (Design tab only) */}
      {activeTab === 'design' && (
        <div
          style={{
            flexShrink: 0,
            borderTop: '1px solid #e5e7eb',
            padding: '12px 24px',
            backgroundColor: '#fff',
            display: 'flex',
            gap: 8,
            alignItems: 'center',
          }}
        >
          <div style={{ flex: 1, position: 'relative' }}>
            <input
              value={newTerm}
              onChange={(e) => setNewTerm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddItem()}
              placeholder="Add term to extract..."
              style={{
                width: '100%',
                padding: '10px 70px 10px 14px',
                fontSize: 13,
                fontFamily: 'inherit',
                border: '1px solid #d1d5db',
                borderRadius: 8,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            <button
              onClick={handleAddItem}
              style={{
                position: 'absolute',
                right: 4,
                top: '50%',
                transform: 'translateY(-50%)',
                padding: '6px 14px',
                fontSize: 12,
                fontWeight: 700,
                fontFamily: 'inherit',
                borderRadius: 6,
                border: 'none',
                backgroundColor: '#191919',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              Add
            </button>
          </div>
          <button
            onClick={handleRun}
            disabled={running || selectedDocUuids.length === 0}
            className="bg-highlight text-highlight-text font-bold hover:brightness-90 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '10px 20px',
              fontSize: 13,
              fontFamily: 'inherit',
              borderRadius: 'var(--ui-radius, 8px)',
              border: 'none',
              cursor: running || selectedDocUuids.length === 0 ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {running ? (
              <>
                <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />
                RUNNING...
              </>
            ) : (
              'RUN'
            )}
          </button>
        </div>
      )}

    </div>
  )
}

/* ── Design Tab ── */

const AI_TIPS: { text: string; condition?: (ctx: { mode: string; chunking: boolean; repetition: boolean; docCount: number; itemCount: number }) => boolean }[] = [
  { text: 'The AI is reading through your documents and identifying the requested fields...' },
  { text: 'Each extraction field is matched against the document content using natural language understanding.' },
  { text: 'Two-pass mode uses a draft pass to reason about the document, then a structured pass to produce clean results.', condition: (c) => c.mode === 'two_pass' },
  { text: 'Pass 1 lets the model "think" freely about the document before committing to final values.', condition: (c) => c.mode === 'two_pass' },
  { text: 'Key chunking splits large field lists into smaller batches so the AI can focus on each group.', condition: (c) => c.chunking },
  { text: 'Repetition mode runs the extraction multiple times and uses consensus to improve accuracy.', condition: (c) => c.repetition },
  { text: 'Structured output mode constrains the AI to return valid JSON, reducing formatting errors.' },
  { text: 'The AI processes each document independently so results stay isolated and accurate.', condition: (c) => c.docCount > 1 },
  { text: 'Longer documents may take more time — the AI is reading the full text to find your fields.' },
  { text: 'Tip: You can customize thinking and structured modes per extraction in the Advanced tab.' },
  { text: 'The model maps each field name to the most relevant passage in your document.' },
  { text: 'Extraction results are generated in a single structured response for consistency.' },
]

function useRotatingTip(running: boolean, config: ExtractionConfig, docCount: number, itemCount: number) {
  const [tipIdx, setTipIdx] = useState(0)

  const mode = config.mode ?? 'one_pass'
  const chunking = config.key_chunking?.enabled ?? false
  const repetition = config.repetition?.enabled ?? false
  const ctx = { mode, chunking, repetition, docCount, itemCount }

  const applicable = AI_TIPS.filter(t => !t.condition || t.condition(ctx))

  useEffect(() => {
    if (!running) { setTipIdx(0); return }
    const interval = setInterval(() => {
      setTipIdx(prev => (prev + 1) % applicable.length)
    }, 5000)
    return () => clearInterval(interval)
  }, [running, applicable.length])

  return running && applicable.length > 0 ? applicable[tipIdx % applicable.length].text : null
}

function DesignTab({
  items,
  itemsLoading,
  results,
  hasResults,
  running,
  config,
  docCount,
  onExport,
  onRemoveItem,
  onUpdateItem,
  onReorder,
  searchSetUuid,
  onHighlightValue,
}: {
  items: { id: string; searchphrase: string; is_optional: boolean; enum_values: string[] }[]
  itemsLoading: boolean
  results: Record<string, string>
  hasResults: boolean
  running: boolean
  config: ExtractionConfig
  docCount: number
  onExport: () => void
  onRemoveItem: (id: string) => void
  onUpdateItem: (id: string, data: { searchphrase?: string; title?: string; is_optional?: boolean; enum_values?: string[] }) => void
  onReorder: (itemIds: string[]) => void
  searchSetUuid?: string
  onHighlightValue: (terms: string[]) => void
}) {
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [expandedSettingsId, setExpandedSettingsId] = useState<string | null>(null)
  const [enumDraft, setEnumDraft] = useState('')
  const tip = useRotatingTip(running, config, docCount, items.length)

  const handleDragStart = (idx: number) => {
    setDragIdx(idx)
  }

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    setOverIdx(idx)
  }

  const handleDrop = (idx: number) => {
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null)
      setOverIdx(null)
      return
    }
    const reordered = [...items]
    const [moved] = reordered.splice(dragIdx, 1)
    reordered.splice(idx, 0, moved)
    onReorder(reordered.map(i => i.id))
    setDragIdx(null)
    setOverIdx(null)
  }

  const handleDragEnd = () => {
    setDragIdx(null)
    setOverIdx(null)
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Section header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>Extractions</div>
        {hasResults && (
          <button
            onClick={onExport}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 12,
              color: '#2563eb',
              fontFamily: 'inherit',
              padding: 0,
            }}
          >
            <Copy style={{ width: 12, height: 12 }} />
            Export
          </button>
        )}
      </div>

      {/* Running status banner */}
      {running && tip && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            padding: '14px 16px',
            marginBottom: 16,
            backgroundColor: '#f0f4ff',
            border: '1px solid #dbeafe',
            borderRadius: 8,
          }}
        >
          <Loader2
            style={{
              width: 16,
              height: 16,
              color: '#3b82f6',
              animation: 'spin 1s linear infinite',
              flexShrink: 0,
              marginTop: 1,
            }}
          />
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#1e40af', marginBottom: 3 }}>
              Extracting...
            </div>
            <div
              key={tip}
              style={{
                fontSize: 13,
                color: '#3b5998',
                lineHeight: 1.45,
                animation: 'fadeIn 0.4s ease',
              }}
            >
              {tip}
            </div>
          </div>
          <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }`}</style>
        </div>
      )}

      {itemsLoading ? (
        <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
          Loading...
        </div>
      ) : items.length === 0 ? (
        <ExtractionTutorial />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {items.map((item, idx) => {
            const resultVal = results[item.searchphrase]
            const isDragging = dragIdx === idx
            const isOver = overIdx === idx && dragIdx !== idx
            return (
              <div
                key={item.id}
                draggable
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDrop={() => handleDrop(idx)}
                onDragEnd={handleDragEnd}
                style={{
                  padding: '10px 0',
                  borderBottom: '1px solid #f0f0f0',
                  opacity: isDragging ? 0.4 : 1,
                  borderTop: isOver ? '2px solid var(--highlight-color, #eab308)' : '2px solid transparent',
                  transition: 'opacity 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <GripVertical
                    style={{
                      width: 14,
                      height: 14,
                      color: '#d1d5db',
                      cursor: 'grab',
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: '#9ca3af',
                      width: 20,
                      textAlign: 'right',
                      flexShrink: 0,
                      marginRight: 4,
                    }}
                  >
                    {idx + 1}
                  </span>
                  {editingId === item.id ? (
                    <input
                      autoFocus
                      value={editDraft}
                      onChange={(e) => setEditDraft(e.target.value)}
                      onBlur={() => {
                        const trimmed = editDraft.trim()
                        if (trimmed && trimmed !== item.searchphrase) {
                          onUpdateItem(item.id, { searchphrase: trimmed, title: trimmed })
                        }
                        setEditingId(null)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      style={{
                        flex: 1,
                        fontSize: 14,
                        fontFamily: 'inherit',
                        color: '#202124',
                        border: '1px solid #d1d5db',
                        borderRadius: 4,
                        padding: '2px 6px',
                        outline: 'none',
                      }}
                    />
                  ) : (
                    <span
                      onDoubleClick={() => {
                        setEditingId(item.id)
                        setEditDraft(item.searchphrase)
                      }}
                      style={{ fontSize: 14, color: '#202124', flex: 1, cursor: 'text', display: 'flex', alignItems: 'center', gap: 4 }}
                    >
                      {item.searchphrase}
                      {item.is_optional && (
                        <span style={{ fontSize: 10, color: '#6b7280', background: '#f3f4f6', borderRadius: 3, padding: '1px 4px', fontWeight: 500 }}>opt</span>
                      )}
                      {item.enum_values.length > 0 && (
                        <span style={{ fontSize: 10, color: '#7c3aed', background: '#f5f3ff', borderRadius: 3, padding: '1px 4px', fontWeight: 500 }}>{item.enum_values.length}</span>
                      )}
                    </span>
                  )}
                  <button
                    onClick={() => {
                      const opening = expandedSettingsId !== item.id
                      setExpandedSettingsId(opening ? item.id : null)
                      if (opening) setEnumDraft(item.enum_values.join(', '))
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 4,
                      color: '#9ca3af',
                      display: 'flex',
                      flexShrink: 0,
                    }}
                    title="Field settings"
                  >
                    {expandedSettingsId === item.id
                      ? <ChevronDown style={{ width: 14, height: 14 }} />
                      : <ChevronRight style={{ width: 14, height: 14 }} />
                    }
                  </button>
                  <button
                    onClick={() => onRemoveItem(item.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 4,
                      color: '#9ca3af',
                      display: 'flex',
                      flexShrink: 0,
                    }}
                  >
                    <X style={{ width: 14, height: 14 }} />
                  </button>
                </div>
                {resultVal !== undefined && (
                  <div
                    onClick={() => {
                      if (resultVal && resultVal !== 'N/A') {
                        onHighlightValue([resultVal])
                        navigator.clipboard.writeText(resultVal).catch(() => {})
                      }
                    }}
                    style={{
                      marginTop: 4,
                      marginLeft: 42,
                      fontSize: 13,
                      fontWeight: 600,
                      color: '#202124',
                      cursor: resultVal && resultVal !== 'N/A' ? 'pointer' : 'default',
                      borderRadius: 4,
                      padding: '2px 4px',
                      transition: 'background-color 0.15s',
                    }}
                    onMouseEnter={e => {
                      if (resultVal && resultVal !== 'N/A')
                        (e.currentTarget as HTMLElement).style.backgroundColor = '#fef9c3'
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent'
                    }}
                    title={resultVal && resultVal !== 'N/A' ? 'Click to highlight in PDF' : undefined}
                  >
                    {resultVal}
                  </div>
                )}
                {expandedSettingsId === item.id && (
                  <div style={{
                    marginTop: 6,
                    marginLeft: 42,
                    padding: '8px 10px',
                    background: '#f9fafb',
                    borderRadius: 6,
                    border: '1px solid #e5e7eb',
                    fontSize: 12,
                  }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', marginBottom: 8 }}>
                      <input
                        type="checkbox"
                        checked={item.is_optional}
                        onChange={() => onUpdateItem(item.id, { is_optional: !item.is_optional })}
                        style={{ accentColor: '#2563eb' }}
                      />
                      <span style={{ color: '#374151', fontWeight: 500 }}>Optional</span>
                      <span style={{ color: '#9ca3af' }}>&mdash; skip accuracy penalty when not found</span>
                    </label>
                    <div>
                      <div style={{ color: '#374151', fontWeight: 500, marginBottom: 4 }}>Allowed values</div>
                      <input
                        value={enumDraft}
                        onChange={(e) => setEnumDraft(e.target.value)}
                        onBlur={() => {
                          const vals = enumDraft.split(',').map(v => v.trim()).filter(Boolean)
                          onUpdateItem(item.id, { enum_values: vals })
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                        }}
                        placeholder="e.g. USD, EUR, GBP"
                        style={{
                          width: '100%',
                          fontSize: 12,
                          fontFamily: 'inherit',
                          color: '#202124',
                          border: '1px solid #d1d5db',
                          borderRadius: 4,
                          padding: '4px 8px',
                          outline: 'none',
                          boxSizing: 'border-box',
                        }}
                      />
                      <div style={{ color: '#9ca3af', fontSize: 11, marginTop: 3 }}>
                        Comma-separated. LLM will pick from these values.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Quality Pulse card */}
      <QualityPulse searchSetUuid={searchSetUuid} itemCount={items.length} />

    </div>
  )
}

/* ── Quality Pulse Card ── */

function QualityPulse({ searchSetUuid, itemCount = 0 }: { searchSetUuid?: string; itemCount?: number }) {
  const [status, setStatus] = useState<QualityStatus | null>(null)

  useEffect(() => {
    if (!searchSetUuid) return
    getQualityStatus(searchSetUuid).then(setStatus).catch(() => {})
  }, [searchSetUuid])

  if (!status || !searchSetUuid) return null

  if (status.status === 'unvalidated') {
    if (itemCount === 0) return null
    return (
      <div style={{
        marginTop: 20, padding: 16, border: '1px solid #e5e7eb',
        borderRadius: 8, backgroundColor: '#fafafa',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <Shield style={{ width: 20, height: 20, color: '#9ca3af', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>No validation data yet</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
            Run validation to check extraction reliability
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      marginTop: 20, padding: 16,
      border: status.config_changed ? '1px solid #fde68a' : '1px solid #e5e7eb',
      borderRadius: 8,
      backgroundColor: status.config_changed ? '#fffbeb' : '#fafafa',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <Shield style={{
        width: 20, height: 20, flexShrink: 0,
        color: status.config_changed ? '#d97706' : status.tier === 'excellent' ? '#16a34a' : status.tier === 'good' ? '#2563eb' : '#d97706',
      }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <QualityBadge tier={status.tier} score={status.score} />
          {status.last_validated_at && (
            <span style={{ fontSize: 11, color: '#9ca3af' }}>
              {relativeTime(status.last_validated_at)}
            </span>
          )}
        </div>
        {status.config_changed && (
          <div style={{ fontSize: 12, color: '#92400e', marginTop: 4 }}>
            Config changed since last validation &mdash; re-validate for accurate results
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Tools Tab ── */

function ToolsTab({
  onClone,
  onDelete,
  onAttachTemplate,
  onGenerateTemplate,
  onExportPdf,
  onExportDefinition,
  onImportDefinition,
  onBuildFromDocument,
  buildingFromDoc,
  attachingTemplate,
  generatingTemplate,
  exportingPdf,
  hasDocuments,
  hasResults,
  hasTemplate,
  hasItems,
}: {
  onClone: () => void
  onDelete: () => void
  onAttachTemplate: () => void
  onGenerateTemplate: () => void
  onExportPdf: () => void
  onExportDefinition: () => void
  onImportDefinition: () => void
  onBuildFromDocument: () => void
  buildingFromDoc: boolean
  attachingTemplate: boolean
  generatingTemplate: boolean
  exportingPdf: boolean
  hasDocuments: boolean
  hasResults: boolean
  hasTemplate: boolean
  hasItems: boolean
}) {
  return (
    <div style={{ padding: 24 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 16,
        }}
      >
        {/* From Document */}
        <ToolCard
          title={buildingFromDoc ? 'Building...' : 'From Document'}
          description={
            !hasDocuments
              ? 'Select a document first, then use AI to generate extraction fields'
              : 'Build extraction from a selected document using AI'
          }
          onClick={onBuildFromDocument}
          disabled={buildingFromDoc || !hasDocuments}
        />
        {/* Clone */}
        <ToolCard
          title="Clone"
          description="Create a copy of this extraction"
          onClick={onClone}
        />
        {/* Attach Template */}
        <ToolCard
          title={attachingTemplate ? 'Attaching...' : hasTemplate ? 'Replace Template' : 'Attach Template'}
          description={
            hasTemplate
              ? 'A fillable PDF template is attached — click to replace it'
              : 'Upload a fillable PDF to auto-generate extraction fields and enable PDF export'
          }
          onClick={onAttachTemplate}
          disabled={attachingTemplate || generatingTemplate}
          secondaryAction={{
            label: generatingTemplate ? 'Generating...' : 'Generate example from fields →',
            onClick: onGenerateTemplate,
            disabled: generatingTemplate || attachingTemplate || !hasItems,
          }}
        />
        {/* Export PDF */}
        <ToolCard
          title={exportingPdf ? 'Exporting...' : 'Export PDF'}
          description={
            hasTemplate
              ? 'Download a filled copy of the PDF template with extracted values'
              : 'Download extraction results as a PDF report'
          }
          onClick={onExportPdf}
          disabled={exportingPdf || !hasResults}
        />
        {/* Export Definition */}
        <ToolCard
          title="Export Definition"
          description="Download as a shareable JSON file"
          onClick={onExportDefinition}
        />
        {/* Import Definition */}
        <ToolCard
          title="Import Definition"
          description="Create a new extraction from an exported JSON file"
          onClick={onImportDefinition}
        />
        {/* Delete */}
        <ToolCard
          title="Delete"
          description="Permanently delete this extraction"
          danger
          onClick={onDelete}
          style={{ gridColumn: '1 / -1' }}
        />
      </div>
    </div>
  )
}

function ToolCard({
  title,
  description,
  disabled,
  danger,
  onClick,
  style,
  secondaryAction,
}: {
  title: string
  description: string
  disabled?: boolean
  danger?: boolean
  onClick: () => void
  style?: React.CSSProperties
  secondaryAction?: { label: string; onClick: () => void; disabled?: boolean }
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: 16,
        border: danger ? '1px solid #fecaca' : '1px solid #e5e7eb',
        borderRadius: 8,
        backgroundColor: disabled ? '#f9fafb' : danger ? '#fef2f2' : '#fff',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        textAlign: 'left',
        fontFamily: 'inherit',
        transition: 'box-shadow 0.15s',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 14,
          fontWeight: 600,
          color: danger ? '#dc2626' : '#202124',
        }}
      >
        {danger && <Trash2 style={{ width: 14, height: 14 }} />}
        {title}
      </div>
      <div style={{ fontSize: 12, color: '#5f6368', lineHeight: 1.4 }}>{description}</div>
      {secondaryAction && (
        <>
          <div style={{ borderTop: '1px solid #f3f4f6', marginTop: 4 }} />
          <span
            role="button"
            onClick={(e) => {
              e.stopPropagation()
              if (!secondaryAction.disabled) secondaryAction.onClick()
            }}
            style={{
              fontSize: 11,
              color: secondaryAction.disabled ? '#9ca3af' : '#2563eb',
              cursor: secondaryAction.disabled ? 'not-allowed' : 'pointer',
              fontWeight: 500,
              paddingTop: 2,
            }}
          >
            {secondaryAction.label}
          </span>
        </>
      )}
    </button>
  )
}

/* ── Advanced Tab ── */

function AdvancedTab({
  config,
  useDefaults,
  onSetUseDefaults,
  onSaveConfig,
}: {
  config: ExtractionConfig
  useDefaults: boolean
  onSetUseDefaults: (v: boolean) => void
  onSaveConfig: (c: ExtractionConfig) => void
}) {
  const mode = config.mode ?? 'one_pass'
  const [models, setModels] = useState<ModelInfo[]>([])

  useEffect(() => {
    if (!useDefaults && models.length === 0) {
      getModels().then(setModels).catch(() => {})
    }
  }, [useDefaults, models.length])

  const updateField = (patch: Partial<ExtractionConfig>) => {
    onSaveConfig({ ...config, ...patch })
  }

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Use system defaults */}
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={useDefaults}
          onChange={(e) => onSetUseDefaults(e.target.checked)}
        />
        <span style={{ fontSize: 14, fontWeight: 500, color: '#202124' }}>
          Use system defaults
        </span>
      </label>

      {!useDefaults && (
        <>
          {/* Mode selector */}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 6 }}>
              Mode
            </div>
            <select
              value={mode}
              onChange={(e) =>
                updateField({ mode: e.target.value as 'one_pass' | 'two_pass' })
              }
              style={{
                fontSize: 13,
                fontFamily: 'inherit',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                padding: '6px 10px',
                backgroundColor: '#fff',
              }}
            >
              <option value="one_pass">One Pass</option>
              <option value="two_pass">Two Pass</option>
            </select>
          </div>

          {/* One-pass settings */}
          {mode === 'one_pass' && (
            <PassSettings
              label="One-Pass Settings"
              value={config.one_pass ?? {}}
              onChange={(v) => updateField({ one_pass: v })}
              models={models}
            />
          )}

          {/* Two-pass settings */}
          {mode === 'two_pass' && (
            <>
              <PassSettings
                label="Pass 1 - Draft"
                value={config.two_pass?.pass1 ?? {}}
                onChange={(v) =>
                  updateField({
                    two_pass: { ...config.two_pass, pass1: v },
                  })
                }
                models={models}
              />
              <PassSettings
                label="Pass 2 - Final"
                value={config.two_pass?.pass2 ?? {}}
                onChange={(v) =>
                  updateField({
                    two_pass: { ...config.two_pass, pass2: v },
                  })
                }
                models={models}
              />
            </>
          )}

          {/* Key Chunking */}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 6 }}>
              Key Chunking
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={config.key_chunking?.enabled ?? false}
                onChange={(e) =>
                  updateField({
                    key_chunking: {
                      ...config.key_chunking,
                      enabled: e.target.checked,
                    },
                  })
                }
              />
              <span style={{ fontSize: 13, color: '#374151' }}>Enable key chunking</span>
            </label>
            {config.key_chunking?.enabled && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ fontSize: 13, color: '#5f6368' }}>Max keys per chunk:</label>
                <input
                  type="number"
                  min={1}
                  value={config.key_chunking?.max_keys ?? 10}
                  onChange={(e) =>
                    updateField({
                      key_chunking: {
                        ...config.key_chunking,
                        enabled: true,
                        max_keys: parseInt(e.target.value) || 10,
                      },
                    })
                  }
                  style={{
                    width: 60,
                    fontSize: 13,
                    fontFamily: 'inherit',
                    border: '1px solid #d1d5db',
                    borderRadius: 6,
                    padding: '4px 8px',
                  }}
                />
              </div>
            )}
          </div>

          {/* Repetition / Consensus */}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 6 }}>
              Repetition / Consensus
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={config.repetition?.enabled ?? false}
                onChange={(e) =>
                  updateField({
                    repetition: { enabled: e.target.checked },
                  })
                }
              />
              <span style={{ fontSize: 13, color: '#374151' }}>Enable repetition</span>
            </label>
            <div style={{ marginTop: 4, fontSize: 12, color: '#5f6368' }}>
              Run the extraction multiple times and use consensus to improve accuracy.
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function PassSettings({
  label,
  value,
  onChange,
  models,
}: {
  label: string
  value: { thinking?: boolean; structured?: boolean; model?: string }
  onChange: (v: { thinking?: boolean; structured?: boolean; model?: string }) => void
  models: ModelInfo[]
}) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 4 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={value.thinking ?? false}
            onChange={(e) => onChange({ ...value, thinking: e.target.checked })}
          />
          <span style={{ fontSize: 13, color: '#374151' }}>Thinking</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={value.structured ?? false}
            onChange={(e) => onChange({ ...value, structured: e.target.checked })}
          />
          <span style={{ fontSize: 13, color: '#374151' }}>Structured</span>
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
          <select
            value={value.model ?? ''}
            onChange={(e) => onChange({ ...value, model: e.target.value || undefined })}
            style={{
              width: 220,
              fontSize: 13,
              fontFamily: 'inherit',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              padding: '6px 10px',
              backgroundColor: '#fff',
            }}
          >
            <option value="">System Default</option>
            {models.map(m => (
              <option key={m.tag} value={m.name}>
                {m.tag || m.name}{m.external ? ' (External)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

/* ── Validation Progress ── */

interface ValidationProgressState {
  sourceIndex: number
  runIndex: number
  phase: string
  pct: number
  elapsed: number
}

function useValidationProgress(
  validating: boolean,
  numSources: number,
  numRuns: number,
  numFields: number,
  config: ExtractionConfig,
): ValidationProgressState {
  const [state, setState] = useState<ValidationProgressState>({
    sourceIndex: 0, runIndex: 0, phase: '', pct: 0, elapsed: 0,
  })
  const startRef = useCallback(() => Date.now(), [])

  useEffect(() => {
    if (!validating) {
      // Brief 100% flash before reset so the bar doesn't jump from 99→0
      if (state.pct > 0) {
        setState(prev => ({ ...prev, pct: 100, phase: 'Complete' }))
        const t = setTimeout(() => setState({ sourceIndex: 0, runIndex: 0, phase: '', pct: 0, elapsed: 0 }), 600)
        return () => clearTimeout(t)
      }
      return
    }

    const start = startRef()
    const mode = config.mode ?? 'one_pass'
    const passCount = mode === 'two_pass' ? 2 : 1
    const hasConsensus = config.repetition?.enabled ?? false
    const consensusMultiplier = hasConsensus ? 3 : 1

    // Each source×run = one "step". Each step has sub-phases.
    const totalSteps = numSources * numRuns
    const secsPerStep = passCount * consensusMultiplier * 12 // ~12s per LLM call (conservative)
    const extractionEstSecs = totalSteps * secsPerStep

    // Never-stalling progress: linear to 90% over the estimated time,
    // then a perpetual slow crawl toward 99% that keeps visibly moving.
    const interval = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000

      let rawPct: number
      if (elapsed < extractionEstSecs) {
        // Linear phase: steady progress up to 90%
        rawPct = (elapsed / extractionEstSecs) * 0.90
      } else {
        // Overtime: logarithmic crawl from 90% toward 99%.
        // Keeps moving ~1% every 30s of overtime so it never looks stuck.
        const overtime = elapsed - extractionEstSecs
        rawPct = 0.90 + 0.09 * (overtime / (overtime + 60))
      }
      rawPct = Math.min(0.99, rawPct)

      // Map pct to source/run indices
      const stepProgress = Math.min(rawPct / 0.90, 1) * totalSteps
      const currentStep = Math.min(Math.floor(stepProgress), totalSteps - 1)
      const si = Math.floor(currentStep / numRuns)
      const ri = currentStep % numRuns

      // Phase label
      let phase: string
      if (elapsed >= extractionEstSecs) {
        phase = 'Waiting for LLM responses...'
      } else {
        const stepFrac = stepProgress - currentStep
        if (mode === 'two_pass') {
          if (stepFrac < 0.4) phase = 'Pass 1 — Draft extraction'
          else if (stepFrac < 0.8) phase = 'Pass 2 — Structured extraction'
          else phase = 'Computing field metrics'
        } else {
          if (stepFrac < 0.7) phase = 'Extracting fields'
          else phase = 'Computing field metrics'
        }
        if (hasConsensus && stepFrac < 0.7) {
          phase = 'Consensus extraction (3x)'
        }
      }

      setState({
        sourceIndex: si,
        runIndex: ri,
        phase,
        pct: Math.round(rawPct * 100),
        elapsed: Math.round(elapsed),
      })
    }, 400)

    return () => clearInterval(interval)
  }, [validating, numSources, numRuns, numFields, config.mode, config.repetition?.enabled, startRef])

  return state
}

function ValidationProgressDisplay({
  progress,
  sources,
  numRuns,
  numFields,
  config,
}: {
  progress: ValidationProgressState
  sources: SourceLocal[]
  numRuns: number
  numFields: number
  config: ExtractionConfig
}) {
  const mode = config.mode ?? 'one_pass'
  const modeLabel = mode === 'two_pass' ? 'Two-Pass' : 'One-Pass'
  const hasThinking = mode === 'two_pass'
    ? (config.two_pass?.pass1?.thinking ?? false)
    : (config.one_pass?.thinking ?? false)
  const hasStructured = mode === 'two_pass'
    ? (config.two_pass?.pass2?.structured ?? false)
    : (config.one_pass?.structured ?? false)
  const hasConsensus = config.repetition?.enabled ?? false
  const hasChunking = config.key_chunking?.enabled ?? false
  const modelName = (mode === 'two_pass' ? config.two_pass?.pass1?.model : config.one_pass?.model) || 'system default'

  return (
    <div style={{
      border: '1px solid #dbeafe', borderRadius: 10, padding: 20,
      backgroundColor: '#f0f5ff',
    }}>
      {/* Progress bar */}
      <div style={{
        height: 6, borderRadius: 3, backgroundColor: '#dbeafe',
        marginBottom: 16, overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: 3,
          backgroundColor: '#3b82f6',
          width: `${progress.pct}%`,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Current operation */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <Loader2 style={{ width: 16, height: 16, color: '#3b82f6', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#1e40af' }}>
            Running {sources.length} {sources.length === 1 ? 'source' : 'sources'} &times; {numRuns} {numRuns === 1 ? 'replicate' : 'replicates'}
          </div>
          <div style={{ fontSize: 12, color: '#3b5998', marginTop: 2 }}>
            {progress.phase}
          </div>
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 20, fontWeight: 700, color: '#3b82f6' }}>
          {progress.pct}%
        </div>
      </div>

      {/* Config details */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, padding: '3px 8px', borderRadius: 4,
          backgroundColor: '#dbeafe', color: '#1e40af', fontWeight: 500,
        }}>
          {modeLabel}
        </span>
        <span style={{
          fontSize: 11, padding: '3px 8px', borderRadius: 4,
          backgroundColor: '#dbeafe', color: '#1e40af', fontWeight: 500,
        }}>
          Model: {modelName}
        </span>
        <span style={{
          fontSize: 11, padding: '3px 8px', borderRadius: 4,
          backgroundColor: '#dbeafe', color: '#1e40af', fontWeight: 500,
        }}>
          {numFields} fields
        </span>
        {hasThinking && (
          <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, backgroundColor: '#e0e7ff', color: '#4338ca', fontWeight: 500 }}>
            Thinking
          </span>
        )}
        {hasStructured && (
          <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, backgroundColor: '#e0e7ff', color: '#4338ca', fontWeight: 500 }}>
            Structured
          </span>
        )}
        {hasConsensus && (
          <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, backgroundColor: '#fef3c7', color: '#92400e', fontWeight: 500 }}>
            Consensus
          </span>
        )}
        {hasChunking && (
          <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4, backgroundColor: '#fef3c7', color: '#92400e', fontWeight: 500 }}>
            Chunking
          </span>
        )}
      </div>

      {/* Elapsed time */}
      <div style={{ marginTop: 10, fontSize: 11, color: '#6b7280' }}>
        Elapsed: {progress.elapsed < 60 ? `${progress.elapsed}s` : `${Math.floor(progress.elapsed / 60)}m ${progress.elapsed % 60}s`}
      </div>
    </div>
  )
}

/* ── Validate Tab ── */

function downloadValidationCSV(results: ValidationV2Result) {
  const csvEscape = (v: string) => {
    if (v.includes(',') || v.includes('"') || v.includes('\n')) {
      return `"${v.replace(/"/g, '""')}"`
    }
    return v
  }

  // Build header: fixed columns + one column per run
  const numRuns = results.num_runs
  const runHeaders = Array.from({ length: numRuns }, (_, i) => `Run ${i + 1}`)
  const headers = [
    'Source', 'Field', 'Expected',
    ...runHeaders,
    'Most Common Value', 'Distinct Values',
    'Accuracy %', 'Consistency %',
    'Accuracy Issues', 'Reproducibility Issues',
  ]

  const rows: string[][] = []

  for (const source of results.sources) {
    for (const field of source.fields) {
      // Accuracy annotation
      const accIssues: string[] = []
      const errorEntries = Object.entries(field.error_types).filter(([, v]) => v > 0)
      if (errorEntries.length > 0) {
        for (const [errType, count] of errorEntries) {
          accIssues.push(`${errType.replace('_', ' ')} (${count}/${numRuns} runs)`)
        }
      }
      if (field.accuracy !== null && field.accuracy < 1) {
        accIssues.push(`${Math.round(field.accuracy * 100)}% accurate`)
      }

      // Reproducibility annotation
      const reproIssues: string[] = []
      if (field.distinct_value_count > 1) {
        reproIssues.push(`${field.distinct_value_count} distinct values across ${numRuns} runs`)
      }
      if (field.consistency < 1) {
        reproIssues.push(`${Math.round(field.consistency * 100)}% consistent`)
      }

      const row = [
        source.source_label,
        field.field_name,
        field.expected ?? '',
        ...field.extracted_values.map(v => v ?? ''),
        field.most_common_value ?? '',
        String(field.distinct_value_count),
        field.accuracy !== null ? String(Math.round(field.accuracy * 100)) : 'N/A',
        String(Math.round(field.consistency * 100)),
        accIssues.join('; '),
        reproIssues.join('; '),
      ]
      rows.push(row)
    }
  }

  const csv = [headers, ...rows].map(row => row.map(csvEscape).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `validation-results-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

interface SourceLocal {
  id: string
  source_type: 'document' | 'text'
  document_uuid?: string
  document_title?: string
  source_text?: string
  expected_values: Record<string, string>
  expanded: boolean
}

function ValidateTab({
  searchSetUuid,
  itemTitle,
  items,
  extractionConfig,
  onUpdateItem,
  onValidationComplete,
}: {
  searchSetUuid: string
  itemTitle?: string
  items: { id: string; searchphrase: string; is_optional: boolean; enum_values: string[] }[]
  extractionConfig: ExtractionConfig
  onUpdateItem: (id: string, data: { is_optional?: boolean; enum_values?: string[] }) => void
  onValidationComplete?: () => void
}) {
  const { selectedDocUuids, viewDocument } = useWorkspace()
  const [sources, setSources] = useState<SourceLocal[]>([])
  const [loadingSources, setLoadingSources] = useState(true)
  const [numRuns, setNumRuns] = useState(3)
  const [validating, setValidating] = useState(false)
  const [results, setResults] = useState<ValidationV2Result | null>(null)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [pendingDocs, setPendingDocs] = useState<{ uuid: string; title: string }[] | null>(null)
  const [autoFilling, setAutoFilling] = useState(false)
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [qualityHistory, setQualityHistory] = useState<QualityHistoryRun[]>([])
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [historyExpanded, setHistoryExpanded] = useState(false)
  const [suggestions, setSuggestions] = useState<string | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false)
  const [tuning, setTuning] = useState(false)
  const [tuningResults, setTuningResults] = useState<TuningResult[] | null>(null)
  const [tuningRecommendation, setTuningRecommendation] = useState<string | null>(null)
  const [fillingSourceId, setFillingSourceId] = useState<string | null>(null)
  const [fillError, setFillError] = useState<string | null>(null)
  const fillAbortRef = useRef<AbortController | null>(null)
  const [showSubmitDialog, setShowSubmitDialog] = useState(false)
  const [submitLibraryResult, setSubmitLibraryResult] = useState<'success' | 'error' | null>(null)
  const progress = useValidationProgress(validating, sources.length, numRuns, items.length, extractionConfig)

  // Debounce timers keyed by source id
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  // Load persisted test cases on mount
  useEffect(() => {
    setLoadingSources(true)
    listTestCases(searchSetUuid)
      .then(cases => {
        const mapped = cases.map(tc => ({
          id: tc.uuid,
          source_type: tc.source_type as 'document' | 'text',
          document_uuid: tc.document_uuid ?? undefined,
          document_title: tc.label || undefined,
          source_text: tc.source_text ?? undefined,
          expected_values: tc.expected_values,
          expanded: false,
        }))
        setSources(mapped)
        if (mapped.length > 0) setSourcesCollapsed(true)
      })
      .catch(() => {})
      .finally(() => setLoadingSources(false))
  }, [searchSetUuid])

  useEffect(() => {
    getExtractionQualityHistory(searchSetUuid)
      .then(r => setQualityHistory(r.runs))
      .catch(() => {})
  }, [searchSetUuid])

  // Cleanup debounce timers on unmount
  useEffect(() => {
    const timers = debounceTimers.current
    return () => { Object.values(timers).forEach(clearTimeout) }
  }, [])

  const handleGetSuggestions = async () => {
    setLoadingSuggestions(true)
    try {
      const res = await getExtractionImprovementSuggestions(searchSetUuid)
      setSuggestions(res.suggestions)
    } catch {
      setSuggestions('Failed to generate suggestions. Please try again.')
    } finally {
      setLoadingSuggestions(false)
    }
  }

  const addDocuments = async (docs: { uuid: string; title: string }[], autoFill: boolean = false) => {
    const created = await Promise.all(
      docs.map(d =>
        createTestCase({
          search_set_uuid: searchSetUuid,
          label: d.title,
          source_type: 'document',
          document_uuid: d.uuid,
          expected_values: {},
        })
      )
    )
    const newSources: SourceLocal[] = created.map((tc, i) => ({
      id: tc.uuid,
      source_type: 'document' as const,
      document_uuid: docs[i].uuid,
      document_title: docs[i].title,
      expected_values: {},
      expanded: false,
    }))
    setSources(prev => [...prev, ...newSources])

    // Auto-fill expected values by running extraction on each document
    if (autoFill) {
      setAutoFilling(true)
      for (const src of newSources) {
        await fillFromExtraction(src).catch(() => {})
      }
      setAutoFilling(false)
    }
  }

  const addTextSource = async () => {
    const tc = await createTestCase({
      search_set_uuid: searchSetUuid,
      label: 'Text Chunk',
      source_type: 'text',
      source_text: '',
      expected_values: {},
    })
    setSources(prev => [
      ...prev,
      {
        id: tc.uuid,
        source_type: 'text',
        source_text: '',
        expected_values: {},
        expanded: true,
      },
    ])
  }

  const removeSource = async (id: string) => {
    setSources(prev => prev.filter(s => s.id !== id))
    // Clear any pending debounce for this source
    if (debounceTimers.current[id]) {
      clearTimeout(debounceTimers.current[id])
      delete debounceTimers.current[id]
    }
    await deleteTestCase(id).catch(() => {})
  }

  const toggleExpanded = (id: string) => {
    setSources(prev => prev.map(s => s.id === id ? { ...s, expanded: !s.expanded } : s))
  }

  const updateSourceText = (id: string, text: string) => {
    setSources(prev => prev.map(s => s.id === id ? { ...s, source_text: text } : s))
    // Debounced save
    if (debounceTimers.current[`text_${id}`]) clearTimeout(debounceTimers.current[`text_${id}`])
    debounceTimers.current[`text_${id}`] = setTimeout(() => {
      updateTestCase(id, { source_text: text }).catch(() => {})
    }, 800)
  }

  const updateExpectedValue = (sourceId: string, field: string, value: string) => {
    let updatedValues: Record<string, string> = {}
    setSources(prev => prev.map(s => {
      if (s.id !== sourceId) return s
      const next = { ...s, expected_values: { ...s.expected_values, [field]: value } }
      updatedValues = next.expected_values
      return next
    }))
    // Debounced save
    const key = `ev_${sourceId}`
    if (debounceTimers.current[key]) clearTimeout(debounceTimers.current[key])
    debounceTimers.current[key] = setTimeout(() => {
      updateTestCase(sourceId, { expected_values: updatedValues }).catch(() => {})
    }, 800)
  }

  const fillFromExtraction = async (src: SourceLocal) => {
    if (!src.document_uuid) return
    // Abort any previous in-flight request
    fillAbortRef.current?.abort()
    const abort = new AbortController()
    fillAbortRef.current = abort
    // 2-minute timeout
    const timeout = setTimeout(() => abort.abort(), 120_000)
    setFillingSourceId(src.id)
    setFillError(null)
    try {
      const resp = await runExtractionSync({
        search_set_uuid: searchSetUuid,
        document_uuids: [src.document_uuid],
      }, abort.signal)
      if (!resp.results || resp.results.length === 0) {
        setFillError('Extraction returned no results. Make sure the document has been processed.')
        return
      }
      const first = resp.results[0]
      if (typeof first === 'object' && first !== null) {
        const newValues: Record<string, string> = {}
        for (const [k, v] of Object.entries(first as Record<string, unknown>)) {
          newValues[k] = v === null ? 'N/A' : String(v)
        }
        setSources(prev => prev.map(s => {
          if (s.id !== src.id) return s
          return { ...s, expected_values: newValues, expanded: true }
        }))
        updateTestCase(src.id, { expected_values: newValues }).catch(() => {})
      }
    } catch (e) {
      if (abort.signal.aborted) {
        setFillError('Extraction timed out. The LLM call may be too slow — try a faster model.')
      } else {
        setFillError(e instanceof Error ? e.message : 'Failed to run extraction')
      }
    } finally {
      clearTimeout(timeout)
      fillAbortRef.current = null
      setFillingSourceId(null)
    }
  }

  const handleRunValidation = async () => {
    setValidating(true)
    setSuggestions(null)
    try {
      const apiSources: ValidationSource[] = sources.map((s, i) => {
        // For document sources, only send label if it's a real title (not a UUID)
        const isUuidLike = s.document_title && /^[0-9a-f-]{20,}$/i.test(s.document_title)
        const label = isUuidLike ? undefined
          : s.document_title || (s.source_type === 'text' ? `Text Chunk ${i + 1}` : undefined)
        return {
          source_type: s.source_type,
          document_uuid: s.document_uuid,
          label,
          source_text: s.source_text,
          expected_values: s.expected_values,
        }
      })
      const res = await runValidationV2({
        search_set_uuid: searchSetUuid,
        sources: apiSources,
        num_runs: numRuns,
      })
      setResults(res)
      getExtractionQualityHistory(searchSetUuid)
        .then(r => setQualityHistory(r.runs))
        .catch(() => {})
      // Auto-fetch LLM suggestions if accuracy or consistency < 95%
      const acc = res.aggregate_accuracy ?? 1
      const con = res.aggregate_consistency ?? 1
      if (acc < 0.95 || con < 0.95) {
        setLoadingSuggestions(true)
        getExtractionImprovementSuggestions(searchSetUuid)
          .then(r => setSuggestions(r.suggestions))
          .catch(() => {})
          .finally(() => setLoadingSuggestions(false))
      }
    } finally {
      setValidating(false)
      onValidationComplete?.()
    }
  }

  const existingUuids = sources.filter(s => s.document_uuid).map(s => s.document_uuid!)

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* 1. Source Management */}
      <div>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 6, marginBottom: sourcesCollapsed ? 0 : 12,
            cursor: sources.length > 0 ? 'pointer' : 'default',
            userSelect: 'none',
          }}
          onClick={() => sources.length > 0 && setSourcesCollapsed(c => !c)}
        >
          {sources.length > 0 && (
            sourcesCollapsed
              ? <ChevronRight style={{ width: 14, height: 14, color: '#9ca3af' }} />
              : <ChevronDown style={{ width: 14, height: 14, color: '#9ca3af' }} />
          )}
          <span style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>
            Validation Sources
          </span>
          {sources.length > 0 && sourcesCollapsed && (
            <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 400 }}>
              ({sources.length} source{sources.length !== 1 ? 's' : ''})
            </span>
          )}
        </div>

        {/* Sample size penalty alert — always visible, even when collapsed */}
        {qualityHistory.length > 0 && qualityHistory[0].score_breakdown && qualityHistory[0].score_breakdown.sample_size_penalty > 0 && (() => {
          const bd = qualityHistory[0].score_breakdown!
          // Hide alert if user has already addressed the issues
          const needMoreDocs = bd.test_cases_needed > 0 && sources.length < 3
          const needMoreRuns = bd.runs_needed > 0 && numRuns < 3
          if (!needMoreDocs && !needMoreRuns) {
            return (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 14px', borderRadius: 8, marginTop: sourcesCollapsed ? 10 : 0, marginBottom: sourcesCollapsed ? 0 : 12,
                backgroundColor: '#ecfdf5', border: '1px solid #a7f3d0',
              }}>
                <ShieldCheck style={{ width: 14, height: 14, color: '#059669', flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: '#065f46' }}>
                  Sample size requirements met. Run validation again to update your score.
                </span>
              </div>
            )
          }
          return (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 10,
              padding: '10px 14px', borderRadius: 8, marginTop: sourcesCollapsed ? 10 : 0, marginBottom: sourcesCollapsed ? 0 : 12,
              backgroundColor: '#fffbeb', border: '1px solid #fde68a',
            }}>
              <AlertTriangle style={{ width: 16, height: 16, color: '#d97706', flexShrink: 0, marginTop: 1 }} />
              <div style={{ flex: 1, fontSize: 12, color: '#92400e', lineHeight: 1.5 }}>
                <strong>Quality score reduced due to low sample size</strong>
                {' '}&mdash;{' '}
                Raw score: <strong>{Math.round(bd.raw_score)}%</strong>, final: <strong>{Math.round(bd.final_score)}%</strong>
                <div style={{ marginTop: 4, fontSize: 11, color: '#78350f' }}>
                  {needMoreDocs && <>Add <strong>{3 - sources.length}</strong> more test document{3 - sources.length !== 1 ? 's' : ''} (need 3 total). </>}
                  {needMoreRuns && <>Increase to <strong>3</strong> runs per validation (currently {numRuns}).</>}
                </div>
              </div>
            </div>
          )
        })()}

        {sourcesCollapsed ? null : loadingSources ? (
          <div style={{
            textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0',
            border: '1px dashed #d1d5db', borderRadius: 8,
          }}>
            <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', display: 'inline-block' }} /> Loading sources...
          </div>
        ) : sources.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: '32px 16px',
            border: '1px dashed #d1d5db', borderRadius: 8,
          }}>
            <Shield style={{ width: 32, height: 32, color: '#9ca3af', margin: '0 auto 12px' }} />
            <div style={{ fontSize: 14, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
              Validate your extraction
            </div>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16, lineHeight: 1.5 }}>
              Add documents with expected values to measure accuracy and consistency across multiple runs.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button
                onClick={() => setShowDocPicker(true)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 16px', fontSize: 13, fontWeight: 600,
                  fontFamily: 'inherit', borderRadius: 8, border: 'none',
                  backgroundColor: '#191919', color: '#fff', cursor: 'pointer',
                }}
              >
                <Plus style={{ width: 14, height: 14 }} /> Add Documents
              </button>
              <button
                onClick={addTextSource}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 16px', fontSize: 13, fontWeight: 500,
                  fontFamily: 'inherit', borderRadius: 8,
                  border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#374151', cursor: 'pointer',
                }}
              >
                Add Text
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {sources.map((src, i) => {
              const isUuidLike = src.document_title && /^[0-9a-f-]{20,}$/i.test(src.document_title)
              const label = (!isUuidLike && src.document_title) || (src.source_type === 'text' ? `Text Chunk ${i + 1}` : `Document ${i + 1}`)
              return (
                <div key={src.id} style={{ padding: '10px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                    <span style={{ fontSize: 13, color: '#202124', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {label}
                    </span>
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 4,
                      backgroundColor: src.source_type === 'text' ? '#eff6ff' : '#fef3c7',
                      color: src.source_type === 'text' ? '#1d4ed8' : '#92400e',
                    }}>
                      {src.source_type}
                    </span>
                    {src.source_type === 'document' && src.document_uuid && (
                      <button
                        onClick={() => viewDocument(src.document_uuid!, src.document_title || label)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                        title="View document"
                      >
                        <Eye style={{ width: 12, height: 12 }} />
                      </button>
                    )}
                    <button
                      onClick={() => toggleExpanded(src.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                      title="Expected Values"
                    >
                      {src.expanded
                        ? <ChevronDown style={{ width: 12, height: 12 }} />
                        : <ChevronRight style={{ width: 12, height: 12 }} />
                      }
                    </button>
                    <button
                      onClick={() => removeSource(src.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                    >
                      <X style={{ width: 12, height: 12 }} />
                    </button>
                  </div>

                  {src.expanded && (
                    <div style={{ marginTop: 8, marginLeft: 22 }}>
                      {/* Text input for text sources */}
                      {src.source_type === 'text' && (
                        <div style={{ marginBottom: 8 }}>
                          <textarea
                            value={src.source_text ?? ''}
                            onChange={e => updateSourceText(src.id, e.target.value)}
                            placeholder="Paste the text to extract from..."
                            rows={3}
                            style={{
                              width: '100%', fontSize: 12, fontFamily: 'inherit',
                              border: '1px solid #d1d5db', borderRadius: 6, padding: '6px 8px',
                              resize: 'vertical', outline: 'none', boxSizing: 'border-box',
                            }}
                          />
                        </div>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#5f6368' }}>
                          Expected Values (optional)
                        </div>
                        {src.source_type === 'document' && src.document_uuid && (
                          <button
                            onClick={() => fillFromExtraction(src)}
                            disabled={fillingSourceId === src.id}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: 3,
                              padding: '2px 7px', fontSize: 11, fontFamily: 'inherit',
                              borderRadius: 4, border: '1px solid #d1d5db', backgroundColor: '#fff',
                              color: fillingSourceId === src.id ? '#9ca3af' : '#5f6368',
                              cursor: fillingSourceId === src.id ? 'not-allowed' : 'pointer',
                            }}
                          >
                            {fillingSourceId === src.id ? (
                              <><Loader2 style={{ width: 10, height: 10, animation: 'spin 1s linear infinite' }} /> Filling...</>
                            ) : (
                              <><Sparkles style={{ width: 10, height: 10 }} /> Fill from extraction</>
                            )}
                          </button>
                        )}
                      </div>
                      {fillError && !fillingSourceId && (
                        <div style={{ fontSize: 11, color: '#dc2626', marginBottom: 6 }}>
                          {fillError}
                        </div>
                      )}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {items.map(item => (
                          <div key={item.id} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{
                                fontSize: 11, color: '#374151', width: 120, flexShrink: 0,
                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                display: 'flex', alignItems: 'center', gap: 3,
                              }}>
                                {item.searchphrase}
                                {item.is_optional && (
                                  <span style={{ fontSize: 9, color: '#6b7280', background: '#f3f4f6', borderRadius: 3, padding: '0px 3px', fontWeight: 500 }}>opt</span>
                                )}
                              </span>
                              <input
                                value={src.expected_values[item.searchphrase] ?? ''}
                                onChange={e => updateExpectedValue(src.id, item.searchphrase, e.target.value)}
                                placeholder={item.is_optional ? 'Expected value (optional field)' : 'Expected value'}
                                style={{
                                  flex: 1, fontSize: 11, fontFamily: 'inherit',
                                  border: '1px solid #d1d5db', borderRadius: 4, padding: '3px 6px',
                                  outline: 'none',
                                  backgroundColor: item.is_optional && !src.expected_values[item.searchphrase] ? '#fafafa' : '#fff',
                                }}
                              />
                              <label
                                title={item.is_optional ? 'Field is optional — no accuracy penalty when blank' : 'Mark as optional'}
                                style={{ display: 'flex', alignItems: 'center', flexShrink: 0, cursor: 'pointer' }}
                              >
                                <input
                                  type="checkbox"
                                  checked={item.is_optional}
                                  onChange={() => onUpdateItem(item.id, { is_optional: !item.is_optional })}
                                  style={{ accentColor: '#2563eb', width: 12, height: 12 }}
                                />
                              </label>
                            </div>
                            {item.enum_values.length > 0 && (
                              <div style={{ marginLeft: 126, fontSize: 10, color: '#7c3aed' }}>
                                Allowed: {item.enum_values.join(', ')}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Add buttons */}
        {!sourcesCollapsed && (
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              onClick={() => setShowDocPicker(true)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
                color: '#202124', cursor: 'pointer',
              }}
            >
              <Plus style={{ width: 12, height: 12 }} /> Add Documents
            </button>
            <button
              onClick={addTextSource}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
                color: '#202124', cursor: 'pointer',
              }}
            >
              <Plus style={{ width: 12, height: 12 }} /> Add Text
            </button>
          </div>
        )}

        {/* Quick add selected docs */}
        {!sourcesCollapsed && selectedDocUuids.length > 0 && (
          <button
            onClick={() => {
              // We don't have titles here, so use UUIDs as labels
              const newDocs = selectedDocUuids
                .filter(uuid => !existingUuids.includes(uuid))
                .map(uuid => ({ uuid, title: `Document ${uuid.slice(0, 8)}...` }))
              if (newDocs.length > 0) setPendingDocs(newDocs)
            }}
            style={{
              marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '6px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 6, border: '1px dashed #93c5fd', backgroundColor: '#eff6ff',
              color: '#1d4ed8', cursor: 'pointer',
            }}
          >
            Add {selectedDocUuids.filter(u => !existingUuids.includes(u)).length} selected document{selectedDocUuids.filter(u => !existingUuids.includes(u)).length !== 1 ? 's' : ''}
          </button>
        )}
      </div>

      {/* 2. Run Controls */}
      <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ fontSize: 13, color: '#5f6368' }}>Replicates:</label>
          <input
            type="number"
            min={1}
            max={10}
            value={numRuns}
            onChange={e => setNumRuns(Math.min(10, Math.max(1, parseInt(e.target.value) || 1)))}
            style={{
              width: 50, fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '6px 8px',
            }}
          />
          <button
            onClick={handleRunValidation}
            disabled={validating || sources.length === 0}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 8, border: 'none',
              backgroundColor: '#191919', color: '#fff',
              cursor: validating || sources.length === 0 ? 'not-allowed' : 'pointer',
              opacity: validating || sources.length === 0 ? 0.5 : 1,
            }}
          >
            {validating ? (
              <><Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> Validating...</>
            ) : (
              <><Play style={{ width: 14, height: 14 }} /> Run Validation</>
            )}
          </button>
          <button
            onClick={async () => {
              setTuning(true)
              setTuningResults(null)
              setTuningRecommendation(null)
              try {
                const res = await findBestSettings(searchSetUuid, numRuns)
                setTuningResults(res.results)
                setTuningRecommendation(res.recommendation)
              } catch (e: unknown) {
                const msg = e instanceof Error ? e.message : 'Failed to find best settings'
                setTuningRecommendation(msg)
              } finally {
                setTuning(false)
              }
            }}
            disabled={tuning || validating || sources.length === 0}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              borderRadius: 8, border: '1px solid #d1d5db', backgroundColor: '#fff',
              color: '#374151',
              cursor: tuning || validating || sources.length === 0 ? 'not-allowed' : 'pointer',
              opacity: tuning || validating || sources.length === 0 ? 0.5 : 1,
            }}
          >
            {tuning ? (
              <><Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> Testing configs...</>
            ) : (
              <><Sparkles style={{ width: 14, height: 14 }} /> Find Best Settings</>
            )}
          </button>
        </div>

        {/* Tuning results */}
        {(tuningResults || tuningRecommendation) && (
          <div style={{
            marginTop: 12, padding: 16, borderRadius: 8,
            border: '1px solid #c4b5fd', backgroundColor: '#f5f3ff',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <Sparkles style={{ width: 14, height: 14, color: '#7c3aed' }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#5b21b6' }}>Settings Comparison</span>
              <button
                onClick={() => { setTuningResults(null); setTuningRecommendation(null) }}
                style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 2 }}
              >
                <X style={{ width: 12, height: 12 }} />
              </button>
            </div>
            {tuningResults && tuningResults.length > 0 && (
              <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse', marginBottom: 10 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #ddd6fe' }}>
                    <th style={{ textAlign: 'left', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Config</th>
                    <th style={{ textAlign: 'left', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Model</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Score</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Acc</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Cons</th>
                    <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {tuningResults.map((r, i) => {
                    const scoreColor = r.score >= 90 ? '#059669' : r.score >= 70 ? '#d97706' : '#dc2626'
                    return (
                      <tr key={i} style={{
                        borderBottom: '1px solid #ede9fe',
                        backgroundColor: i === 0 ? '#ede9fe' : 'transparent',
                      }}>
                        <td style={{ padding: '4px 6px', fontWeight: i === 0 ? 700 : 400 }}>
                          {r.label}{i === 0 && ' *'}
                        </td>
                        <td style={{ padding: '4px 6px', color: '#6b7280', fontSize: 10 }}>{r.model}</td>
                        <td style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600, color: scoreColor }}>
                          {r.error ? '—' : Math.round(r.score)}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right' }}>
                          {r.error ? '—' : `${Math.round(r.accuracy * 100)}%`}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right' }}>
                          {r.error ? '—' : `${Math.round(r.consistency * 100)}%`}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right', color: '#6b7280' }}>
                          {r.error ? '—' : `${r.elapsed_seconds.toFixed(1)}s`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
            {tuningRecommendation && (
              <div style={{ fontSize: 12, color: '#5b21b6', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {tuningRecommendation}
              </div>
            )}
          </div>
        )}

        {/* Progress display */}
        {validating && (
          <div style={{ marginTop: 16 }}>
            <ValidationProgressDisplay
              progress={progress}
              sources={sources}
              numRuns={numRuns}
              numFields={items.length}
              config={extractionConfig}
            />
          </div>
        )}
      </div>

      {/* 3. Quality History — graph only, expandable run table */}
      {qualityHistory.length > 1 && (
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
          backgroundColor: '#fff',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <TrendingUp style={{ width: 14, height: 14, color: '#6b7280' }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Quality History</span>
            <span style={{ fontSize: 11, color: '#9ca3af' }}>({qualityHistory.length} runs)</span>
          </div>
          <div style={{ width: '100%', height: 80 }}>
            <QualityHistoryChart runs={qualityHistory} />
          </div>

          {/* Expand toggle for run details */}
          <button
            onClick={() => setHistoryExpanded(!historyExpanded)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, marginTop: 8,
              fontSize: 11, color: '#6b7280', background: 'none', border: 'none',
              cursor: 'pointer', padding: '4px 0', fontFamily: 'inherit',
            }}
          >
            {historyExpanded
              ? <ChevronDown style={{ width: 12, height: 12 }} />
              : <ChevronRight style={{ width: 12, height: 12 }} />}
            {historyExpanded ? 'Hide run details' : 'Show all runs'}
          </button>

          {/* Collapsible run comparison table */}
          {historyExpanded && (
            <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse', marginTop: 4 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ width: 20, padding: '4px 2px' }} />
                  <th style={{ textAlign: 'left', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Date</th>
                  <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Score</th>
                  <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Acc</th>
                  <th style={{ textAlign: 'right', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Cons</th>
                  <th style={{ textAlign: 'left', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Config</th>
                  <th style={{ textAlign: 'left', padding: '4px 6px', color: '#6b7280', fontWeight: 500 }}>Model</th>
                </tr>
              </thead>
              <tbody>
                {qualityHistory.map((run) => {
                  const scoreColor = run.score >= 90 ? '#059669' : run.score >= 70 ? '#d97706' : '#dc2626'
                  const isExpanded = expandedRunId === run.uuid
                  return (
                    <Fragment key={run.uuid}>
                      <tr
                        style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}
                        onClick={() => setExpandedRunId(isExpanded ? null : run.uuid)}
                      >
                        <td style={{ padding: '4px 2px', color: '#9ca3af' }}>
                          {isExpanded
                            ? <ChevronDown style={{ width: 12, height: 12 }} />
                            : <ChevronRight style={{ width: 12, height: 12 }} />}
                        </td>
                        <td style={{ padding: '4px 6px', color: '#374151' }}>
                          {new Date(run.created_at).toLocaleDateString()}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right', fontWeight: 600, color: scoreColor }}>
                          {Math.round(run.score)}
                          {run.score_breakdown && run.score_breakdown.sample_size_penalty > 0 && (
                            <span title={`Raw score: ${Math.round(run.score_breakdown.raw_score)} (reduced due to small sample size)`}
                              style={{ color: '#d97706', fontSize: 9, marginLeft: 2, verticalAlign: 'super' }}>*</span>
                          )}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right', color: '#374151' }}>
                          {run.accuracy != null ? `${Math.round(run.accuracy * 100)}%` : '—'}
                        </td>
                        <td style={{ padding: '4px 6px', textAlign: 'right', color: '#374151' }}>
                          {run.consistency != null ? `${Math.round(run.consistency * 100)}%` : '—'}
                        </td>
                        <td style={{ padding: '4px 6px' }}>
                          <span style={{
                            display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                            backgroundColor: '#f3f4f6', color: '#4b5563', fontSize: 10,
                          }}>
                            {_summarizeConfig(run.extraction_config)}
                          </span>
                        </td>
                        <td style={{ padding: '4px 6px', color: '#6b7280', fontSize: 10 }}>
                          {run.model || '—'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} style={{ padding: '8px 6px 12px 24px', backgroundColor: '#f9fafb' }}>
                            {run.score_breakdown && run.score_breakdown.sample_size_penalty > 0 && (
                              <div style={{
                                display: 'flex', alignItems: 'flex-start', gap: 8,
                                padding: '8px 12px', marginBottom: 8, borderRadius: 6,
                                backgroundColor: '#fffbeb', border: '1px solid #fde68a',
                              }}>
                                <AlertTriangle style={{ width: 14, height: 14, color: '#d97706', flexShrink: 0, marginTop: 1 }} />
                                <div style={{ fontSize: 11, color: '#92400e', lineHeight: 1.5 }}>
                                  <strong>Score reduced by sample size confidence penalty</strong>
                                  <br />
                                  Raw score: <strong>{Math.round(run.score_breakdown.raw_score)}</strong> → Final: <strong>{Math.round(run.score_breakdown.final_score)}</strong> ({`-${Math.round(run.score_breakdown.sample_size_penalty)} pts`})
                                  <br />
                                  <span style={{ color: '#78350f' }}>
                                    {run.score_breakdown.test_cases_needed > 0 && run.score_breakdown.runs_needed > 0
                                      ? `Add ${run.score_breakdown.test_cases_needed} more test case${run.score_breakdown.test_cases_needed > 1 ? 's' : ''} and increase to ${3} runs per test case to reach full confidence.`
                                      : run.score_breakdown.test_cases_needed > 0
                                        ? `Add ${run.score_breakdown.test_cases_needed} more test case${run.score_breakdown.test_cases_needed > 1 ? 's' : ''} to reach full confidence.`
                                        : `Increase to ${3} runs per test case to reach full confidence.`
                                    }
                                  </span>
                                </div>
                              </div>
                            )}
                            {_renderConfigDetails(run.extraction_config)}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Submit to public library nudge — shown directly after suggestions/history, not in results */}
      {results && (() => {
        // Use the actual quality score (includes sample size penalty) if available
        const latestScore = qualityHistory.length > 0 ? qualityHistory[0].score : null
        const displayScore = latestScore ?? Math.round((results.executive_summary.mean_accuracy ?? 0) * 60 + (results.executive_summary.mean_consistency ?? 0) * 40)
        if (displayScore < 80) return null
        return (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '12px 16px', borderRadius: 8,
            backgroundColor: '#ecfdf5', border: '1px solid #a7f3d0',
          }}>
            <ShieldCheck style={{ width: 20, height: 20, color: '#059669', flexShrink: 0 }} />
            <div style={{ flex: 1, fontSize: 13, color: '#065f46' }}>
              <strong>Great results!</strong> This extraction has a quality score of {Math.round(displayScore)}%. Consider sharing it with the public library so others can benefit.
            </div>
            {submitLibraryResult === 'success' ? (
              <span style={{ fontSize: 12, fontWeight: 600, color: '#059669', whiteSpace: 'nowrap' }}>Submitted!</span>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); setShowSubmitDialog(true) }}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  borderRadius: 6, border: '1px solid #a7f3d0', backgroundColor: '#fff',
                  color: '#059669', cursor: 'pointer', whiteSpace: 'nowrap',
                }}
              >
                Submit to Public Library
              </button>
            )}
            {showSubmitDialog && (
              <VerificationSubmitDialog
                itemKind="search_set"
                itemId={searchSetUuid!}
                itemTitle={itemTitle}
                onClose={() => setShowSubmitDialog(false)}
                onSuccess={() => {
                  setShowSubmitDialog(false)
                  setSubmitLibraryResult('success')
                }}
              />
            )}
          </div>
        )
      })()}

      {/* 4. Results — Executive Summary */}
      {results && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>Results</div>
            <button
              onClick={() => downloadValidationCSV(results)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
                color: '#374151', cursor: 'pointer',
              }}
            >
              <Download style={{ width: 13, height: 13 }} /> Download CSV
            </button>
          </div>

          {/* Executive Summary Card */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12,
            padding: '12px 16px', borderRadius: 8, backgroundColor: '#f9fafb',
            border: '1px solid #e5e7eb',
          }}>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Mean Accuracy</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: _scoreColor(results.executive_summary.mean_accuracy) }}>
                {results.executive_summary.mean_accuracy !== null ? `${Math.round(results.executive_summary.mean_accuracy * 100)}%` : 'N/A'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Mean Consistency</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: _scoreColor(results.executive_summary.mean_consistency) }}>
                {Math.round(results.executive_summary.mean_consistency * 100)}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Perfect Fields</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#202124' }}>
                {results.executive_summary.perfect_fields_count}/{results.executive_summary.total_fields_count}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Std Dev</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#374151' }}>
                {results.executive_summary.run_to_run_std_dev.toFixed(2)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Best Run</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#059669' }}>
                Src {results.executive_summary.best_run.source_index + 1}, Run {results.executive_summary.best_run.run_index + 1} ({results.executive_summary.best_run.correct} correct)
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Worst Run</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#dc2626' }}>
                Src {results.executive_summary.worst_run.source_index + 1}, Run {results.executive_summary.worst_run.run_index + 1} ({results.executive_summary.worst_run.correct} correct)
              </div>
            </div>
          </div>

          {/* LLM Improvement Suggestions */}
          {(suggestions || loadingSuggestions || (
            (results.aggregate_accuracy !== null && results.aggregate_accuracy < 0.95) ||
            results.aggregate_consistency < 0.95
          )) && (
            <div style={{
              border: '1px solid #fde68a', borderRadius: 8, padding: '12px 16px',
              backgroundColor: '#fffbeb',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Sparkles style={{ width: 14, height: 14, color: '#d97706' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#92400e' }}>Improvement Suggestions</span>
                </div>
                {!suggestions && !loadingSuggestions && (
                  <button
                    onClick={handleGetSuggestions}
                    disabled={loadingSuggestions}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                      borderRadius: 6, border: '1px solid #fde68a', backgroundColor: '#fff',
                      color: '#92400e', cursor: 'pointer',
                    }}
                  >
                    Get AI Suggestions
                  </button>
                )}
              </div>
              {loadingSuggestions && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#92400e', marginTop: 8 }}>
                  <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />
                  Analyzing validation results...
                </div>
              )}
              {suggestions && (
                <div
                  className="chat-markdown"
                  style={{ fontSize: 13, color: '#78350f', lineHeight: 1.6, marginTop: 8 }}
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(suggestions) as string) }}
                />
              )}
            </div>
          )}

          {/* 5. Per-Run Reproducibility */}
          {results.executive_summary.per_run_reproducibility.length > 0 && (
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, backgroundColor: '#fff' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 8 }}>Per-Run Reproducibility</div>
              <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <th style={{ textAlign: 'left', padding: '4px 6px', color: '#5f6368', fontWeight: 600 }}>Run #</th>
                    {results.executive_summary.per_run_reproducibility.map(pr => (
                      <th key={pr.source_label} style={{ textAlign: 'center', padding: '4px 6px', color: '#5f6368', fontWeight: 600, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {pr.source_label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: numRuns }).map((_, runIdx) => (
                    <tr key={runIdx} style={{ borderBottom: '1px solid #f0f0f0' }}>
                      <td style={{ padding: '4px 6px', color: '#374151', fontWeight: 500 }}>Run {runIdx + 1}</td>
                      {results.executive_summary.per_run_reproducibility.map(pr => {
                        const correct = pr.runs[runIdx] ?? 0
                        const total = items.length
                        const ratio = total > 0 ? correct / total : 0
                        return (
                          <td key={pr.source_label} style={{ padding: '4px 6px', textAlign: 'center' }}>
                            <span style={{
                              padding: '1px 6px', borderRadius: 4, fontSize: 11,
                              backgroundColor: _scoreBg(ratio), color: _scoreColor(ratio),
                            }}>
                              {correct}
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 6. Per-Source Expandable Details */}
          {results.sources.map((sr, si) => (
            <div key={si} style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
              <button
                onClick={() => setExpandedSource(expandedSource === `${si}` ? null : `${si}`)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '10px 14px', border: 'none', backgroundColor: '#fafafa',
                  cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                }}
              >
                {expandedSource === `${si}`
                  ? <ChevronDown style={{ width: 14, height: 14, color: '#5f6368', flexShrink: 0 }} />
                  : <ChevronRight style={{ width: 14, height: 14, color: '#5f6368', flexShrink: 0 }} />
                }
                <span style={{ fontSize: 13, fontWeight: 600, color: '#202124', flex: 1 }}>{sr.source_label}</span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, backgroundColor: _scoreBg(sr.overall_accuracy), color: _scoreColor(sr.overall_accuracy) }}>
                  {sr.overall_accuracy !== null ? `${Math.round(sr.overall_accuracy * 100)}% acc` : 'N/A'}
                </span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, backgroundColor: _scoreBg(sr.overall_consistency), color: _scoreColor(sr.overall_consistency) }}>
                  {Math.round(sr.overall_consistency * 100)}% cons
                </span>
              </button>

              {expandedSource === `${si}` && (
                <div style={{ padding: '0 14px 14px' }}>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginTop: 8 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Field</th>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Expected</th>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Extracted</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Distinct</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Cons</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Acc</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sr.fields.map(f => {
                        const errorEntries = Object.entries(f.error_types).filter(([, v]) => v > 0)
                        return (
                          <tr key={f.field_name} style={{ borderBottom: '1px solid #f0f0f0' }}>
                            <td style={{ padding: '6px 4px', color: '#202124', fontWeight: 500 }}>{f.field_name}</td>
                            <td style={{ padding: '6px 4px', color: '#5f6368', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.expected ?? '-'}</td>
                            <td style={{ padding: '6px 4px', color: '#202124', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {f.most_common_value ?? 'null'}
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'center', color: '#374151' }}>{f.distinct_value_count}</td>
                            <td style={{ padding: '6px 4px', textAlign: 'center' }}>
                              <span style={{ padding: '1px 6px', borderRadius: 4, backgroundColor: _scoreBg(f.consistency), color: _scoreColor(f.consistency), fontSize: 11 }}>
                                {Math.round(f.consistency * 100)}%
                              </span>
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'center' }}>
                              {f.accuracy !== null ? (
                                <span style={{ padding: '1px 6px', borderRadius: 4, backgroundColor: _scoreBg(f.accuracy), color: _scoreColor(f.accuracy), fontSize: 11 }}>
                                  {Math.round(f.accuracy * 100)}%
                                </span>
                              ) : (
                                <span style={{ color: '#9ca3af', fontSize: 11 }}>N/A</span>
                              )}
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'center', fontSize: 10 }}>
                              {errorEntries.length > 0
                                ? errorEntries.map(([t, c]) => `${t}:${c}`).join(', ')
                                : <span style={{ color: '#9ca3af' }}>-</span>
                              }
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}

          {/* 7. Challenging Fields */}
          {results.challenging_fields.length > 0 && (
            <div style={{
              border: '1px solid #fde68a', borderRadius: 8, padding: 12,
              backgroundColor: '#fffbeb',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <AlertTriangle style={{ width: 14, height: 14, color: '#d97706' }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: '#92400e' }}>Challenging Fields</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {results.challenging_fields.map((cf, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#78350f', display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{cf.field_name}</span>
                    <span style={{ color: '#92400e' }}>({cf.source_label})</span>
                    {cf.accuracy !== null && (
                      <span style={{ padding: '1px 6px', borderRadius: 4, backgroundColor: _scoreBg(cf.accuracy), color: _scoreColor(cf.accuracy), fontSize: 10 }}>
                        {Math.round(cf.accuracy * 100)}% acc
                      </span>
                    )}
                    <span style={{ padding: '1px 6px', borderRadius: 4, backgroundColor: _scoreBg(cf.consistency), color: _scoreColor(cf.consistency), fontSize: 10 }}>
                      {Math.round(cf.consistency * 100)}% cons
                    </span>
                    <span style={{ fontSize: 10, color: '#92400e' }}>({cf.most_common_error})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 8. Error Type Summary */}
          {Object.keys(results.error_type_summary).length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(results.error_type_summary).map(([type, count]) => (
                <span key={type} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '4px 10px', fontSize: 12, borderRadius: 6,
                  backgroundColor: type === 'missing' ? '#fef2f2' : type === 'wrong_value' ? '#fef2f2' : type === 'format_difference' ? '#fffbeb' : '#eff6ff',
                  color: type === 'missing' ? '#dc2626' : type === 'wrong_value' ? '#dc2626' : type === 'format_difference' ? '#d97706' : '#1d4ed8',
                  fontWeight: 600,
                }}>
                  {type.replace('_', ' ')}: {count}
                </span>
              ))}
            </div>
          )}

        </div>
      )}

      {/* Document Picker Dialog */}
      {showDocPicker && (
        <DocumentPickerDialog
          onSelect={(docs) => {
            setShowDocPicker(false)
            setPendingDocs(docs)
          }}
          onClose={() => setShowDocPicker(false)}
          excludeUuids={existingUuids}
        />
      )}

      {/* Auto-populate prompt after selecting documents */}
      {pendingDocs && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{
            backgroundColor: '#fff', borderRadius: 12, padding: 24, maxWidth: 440, width: '90%',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#202124', marginBottom: 8 }}>
              Auto-populate expected values?
            </div>
            <div style={{ fontSize: 13, color: '#5f6368', lineHeight: 1.6, marginBottom: 20 }}>
              Run extraction on {pendingDocs.length === 1 ? 'this document' : `these ${pendingDocs.length} documents`} and
              use the results as expected values. You can review and correct them afterwards.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                disabled={autoFilling}
                onClick={() => {
                  const docs = pendingDocs
                  setPendingDocs(null)
                  addDocuments(docs, false)
                }}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                  borderRadius: 8, border: '1px solid #d1d5db', backgroundColor: '#fff',
                  color: '#374151', cursor: 'pointer',
                }}
              >
                No, add empty
              </button>
              <button
                disabled={autoFilling}
                onClick={() => {
                  const docs = pendingDocs
                  setPendingDocs(null)
                  addDocuments(docs, true)
                }}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                  borderRadius: 8, border: 'none',
                  backgroundColor: '#191919', color: '#fff',
                  cursor: autoFilling ? 'not-allowed' : 'pointer',
                  opacity: autoFilling ? 0.6 : 1,
                }}
              >
                {autoFilling ? 'Extracting...' : 'Yes, auto-populate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function QualityHistoryChart({ runs }: { runs: QualityHistoryRun[] }) {
  const data = [...runs].reverse().map(r => {
    // Use raw score (pre-penalty) for the chart so users see actual quality
    const rawScore = r.score_breakdown?.raw_score ?? r.score
    return {
      date: new Date(r.created_at).toLocaleDateString(),
      score: Math.round(rawScore),
      adjusted: Math.round(r.score),
      hasPenalty: r.score_breakdown ? r.score_breakdown.sample_size_penalty > 0 : false,
    }
  })

  const latestScore = data.length > 0 ? data[data.length - 1].score : 0
  const lineColor = latestScore >= 90 ? '#16a34a' : latestScore >= 70 ? '#d97706' : '#dc2626'

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#9ca3af' }} interval="preserveStartEnd" />
        <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} />
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 6, border: '1px solid #e5e7eb' }}
          formatter={(value: number | undefined, name?: string) => {
            const label = name === 'score' ? 'Quality' : 'Adjusted'
            return [`${value ?? 0}%`, label]
          }}
        />
        <Line type="monotone" dataKey="score" stroke={lineColor} strokeWidth={2} dot={{ r: 2 }} name="score" />
      </LineChart>
    </ResponsiveContainer>
  )
}

function _summarizeConfig(config?: Record<string, unknown> | null): string {
  if (!config || Object.keys(config).length === 0) return 'default'
  if (config.mode === 'two_pass') return 'two_pass'
  if (config.mode === 'one_pass') return 'one_pass'
  return 'default'
}

function _renderConfigDetails(config?: Record<string, unknown> | null): React.ReactNode {
  if (!config || Object.keys(config).length === 0) {
    return <span style={{ fontSize: 11, color: '#9ca3af', fontStyle: 'italic' }}>System defaults were used</span>
  }

  const kvStyle: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 12px', fontSize: 11,
  }
  const labelStyle: React.CSSProperties = { color: '#6b7280', fontWeight: 500 }
  const valStyle: React.CSSProperties = { color: '#374151' }
  const sectionStyle: React.CSSProperties = { fontWeight: 600, color: '#4b5563', fontSize: 11, marginTop: 6, marginBottom: 2 }

  const mode = (config.mode as string) || 'one_pass'
  const onePass = config.one_pass as Record<string, unknown> | undefined
  const twoPass = config.two_pass as Record<string, unknown> | undefined
  const chunking = config.chunking as Record<string, unknown> | undefined
  const repetition = config.repetition as Record<string, unknown> | undefined

  const bool = (v: unknown) => v ? 'Yes' : 'No'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={kvStyle}>
        <span style={labelStyle}>Mode</span>
        <span style={valStyle}>{mode}</span>
      </div>

      {mode === 'one_pass' && onePass && (
        <>
          <div style={sectionStyle}>One-pass settings</div>
          <div style={kvStyle}>
            <span style={labelStyle}>Thinking</span>
            <span style={valStyle}>{bool(onePass.thinking)}</span>
            <span style={labelStyle}>Structured</span>
            <span style={valStyle}>{bool(onePass.structured)}</span>
            {typeof onePass.model === 'string' && <>
              <span style={labelStyle}>Model override</span>
              <span style={valStyle}>{String(onePass.model)}</span>
            </>}
          </div>
        </>
      )}

      {mode === 'two_pass' && twoPass && (() => {
        const p1 = twoPass.pass_1 as Record<string, unknown> | undefined
        const p2 = twoPass.pass_2 as Record<string, unknown> | undefined
        return (
          <>
            {p1 && (
              <>
                <div style={sectionStyle}>Pass 1 (draft)</div>
                <div style={kvStyle}>
                  <span style={labelStyle}>Thinking</span>
                  <span style={valStyle}>{bool(p1.thinking)}</span>
                  <span style={labelStyle}>Structured</span>
                  <span style={valStyle}>{bool(p1.structured)}</span>
                  {typeof p1.model === 'string' && <>
                    <span style={labelStyle}>Model</span>
                    <span style={valStyle}>{String(p1.model)}</span>
                  </>}
                </div>
              </>
            )}
            {p2 && (
              <>
                <div style={sectionStyle}>Pass 2 (final)</div>
                <div style={kvStyle}>
                  <span style={labelStyle}>Thinking</span>
                  <span style={valStyle}>{bool(p2.thinking)}</span>
                  <span style={labelStyle}>Structured</span>
                  <span style={valStyle}>{bool(p2.structured)}</span>
                  {typeof p2.model === 'string' && <>
                    <span style={labelStyle}>Model</span>
                    <span style={valStyle}>{String(p2.model)}</span>
                  </>}
                </div>
              </>
            )}
          </>
        )
      })()}

      {chunking && (
        <>
          <div style={sectionStyle}>Chunking</div>
          <div style={kvStyle}>
            <span style={labelStyle}>Enabled</span>
            <span style={valStyle}>{bool(chunking.enabled)}</span>
            {chunking.max_keys_per_chunk != null && <>
              <span style={labelStyle}>Max keys/chunk</span>
              <span style={valStyle}>{String(chunking.max_keys_per_chunk)}</span>
            </>}
          </div>
        </>
      )}

      {repetition && (
        <>
          <div style={sectionStyle}>Repetition</div>
          <div style={kvStyle}>
            <span style={labelStyle}>Enabled</span>
            <span style={valStyle}>{bool(repetition.enabled)}</span>
          </div>
        </>
      )}
    </div>
  )
}

function _scoreColor(score: number | null): string {
  if (score === null) return '#9ca3af'
  if (score >= 0.9) return '#059669'
  if (score >= 0.7) return '#d97706'
  return '#dc2626'
}

function _scoreBg(score: number | null): string {
  if (score === null) return '#f3f4f6'
  if (score >= 0.9) return '#ecfdf5'
  if (score >= 0.7) return '#fffbeb'
  return '#fef2f2'
}

/* ── Shared ── */

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 24px',
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#fff',
        flexShrink: 0,
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600, color: '#202124', letterSpacing: '-0.01em' }}>
        {title}
      </div>
      <button
        onClick={onClose}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 4,
          borderRadius: 4,
          color: '#5f6368',
          display: 'flex',
        }}
      >
        <X style={{ width: 20, height: 20 }} />
      </button>
    </div>
  )
}
