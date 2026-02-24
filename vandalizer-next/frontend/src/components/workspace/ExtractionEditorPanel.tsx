import React, { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { X, Pencil, Loader2, Copy, Trash2, Star, GripVertical, Plus, ChevronDown, ChevronRight, Play, TrendingUp, Sparkles, FileText, Search, AlertTriangle, Eye } from 'lucide-react'
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
} from '../../api/extractions'
import type { ValidationV2Result, QualityHistoryRun, ValidationSource } from '../../api/extractions'
import { searchDocuments } from '../../api/documents'
import { getModels } from '../../api/config'
import { submitRating } from '../../api/feedback'
import { useLibraries } from '../../hooks/useLibrary'
import { useTeams } from '../../hooks/useTeams'
import { AddToLibraryDialog } from '../library/AddToLibraryDialog'
import type { SearchSet, ModelInfo } from '../../types/workflow'

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
  const { openExtractionId, closeExtraction, selectedDocUuids, setHighlightTerms, bumpActivitySignal } = useWorkspace()
  const { currentTeam } = useTeams()
  const [searchSet, setSearchSet] = useState<SearchSet | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('design')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [newTerm, setNewTerm] = useState('')
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<Record<string, string>>({})
  const [showAddToLibrary, setShowAddToLibrary] = useState(false)
  const { libraries } = useLibraries(currentTeam?.uuid)

  const { items, loading: itemsLoading, refresh: refreshItems, add, remove, update, reorder } =
    useSearchSetItems(openExtractionId)

  const refresh = useCallback(async () => {
    if (!openExtractionId) return
    setLoading(true)
    try {
      const ss = await getSearchSet(openExtractionId)
      setSearchSet(ss)
    } finally {
      setLoading(false)
    }
  }, [openExtractionId])

  useEffect(() => {
    refresh()
    setResults({})
    setActiveTab('design')
  }, [refresh])

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
              }}
            >
              {tab}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {activeTab === 'design' && (
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
              pdfTitle={searchSet?.title ?? ''}
              searchSetUuid={openExtractionId ?? undefined}
              onHighlightValue={setHighlightTerms}
            />
          )}
          {activeTab === 'tools' && (
            <ToolsTab
              onClone={handleClone}
              onDelete={handleDelete}
              onAddToLibrary={() => setShowAddToLibrary(true)}
              onBuildFromDocument={handleBuildFromDocument}
              buildingFromDoc={buildingFromDoc}
              hasDocuments={selectedDocUuids.length > 0}
            />
          )}
          {activeTab === 'validate' && openExtractionId && (
            <ValidateTab
              searchSetUuid={openExtractionId}
              items={items}
              extractionConfig={config}
            />
          )}
          {activeTab === 'advanced' && (
            <AdvancedTab
              config={config}
              useDefaults={useDefaults}
              onSetUseDefaults={setUseDefaults}
              onSaveConfig={saveConfig}
            />
          )}
        </div>

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
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '10px 20px',
              fontSize: 13,
              fontWeight: 700,
              fontFamily: 'inherit',
              borderRadius: 8,
              border: 'none',
              backgroundColor: '#191919',
              color: '#fff',
              cursor: running || selectedDocUuids.length === 0 ? 'not-allowed' : 'pointer',
              opacity: running || selectedDocUuids.length === 0 ? 0.5 : 1,
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

      {showAddToLibrary && openExtractionId && (
        <AddToLibraryDialog
          libraries={libraries}
          itemId={openExtractionId}
          kind="search_set"
          onClose={() => setShowAddToLibrary(false)}
          onAdded={() => setShowAddToLibrary(false)}
        />
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
  pdfTitle,
  searchSetUuid,
  onHighlightValue,
}: {
  items: { id: string; searchphrase: string }[]
  itemsLoading: boolean
  results: Record<string, string>
  hasResults: boolean
  running: boolean
  config: ExtractionConfig
  docCount: number
  onExport: () => void
  onRemoveItem: (id: string) => void
  onUpdateItem: (id: string, data: { searchphrase?: string; title?: string }) => void
  onReorder: (itemIds: string[]) => void
  pdfTitle: string
  searchSetUuid?: string
  onHighlightValue: (terms: string[]) => void
}) {
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
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
        <div
          style={{
            textAlign: 'center',
            color: '#888',
            fontSize: 13,
            padding: '32px 0',
          }}
        >
          Add your first item to begin
        </div>
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
                      style={{ fontSize: 14, color: '#202124', flex: 1, cursor: 'text' }}
                    >
                      {item.searchphrase}
                    </span>
                  )}
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
              </div>
            )
          })}
        </div>
      )}

      {/* Rating widget — shown after results */}
      {hasResults && (
        <RatingWidget
          pdfTitle={pdfTitle}
          resultJson={results}
          searchSetUuid={searchSetUuid}
        />
      )}
    </div>
  )
}

/* ── Rating Widget ── */

function RatingWidget({
  pdfTitle,
  resultJson,
  searchSetUuid,
}: {
  pdfTitle: string
  resultJson: Record<string, string>
  searchSetUuid?: string
}) {
  const [rating, setRating] = useState(0)
  const [hoveredStar, setHoveredStar] = useState(0)
  const [comment, setComment] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (rating === 0) return
    setSubmitting(true)
    try {
      await submitRating({
        pdf_title: pdfTitle,
        rating,
        comment: comment.trim() || undefined,
        result_json: resultJson as Record<string, unknown>,
        search_set_uuid: searchSetUuid,
      })
      setSubmitted(true)
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div
        style={{
          marginTop: 20,
          padding: 16,
          border: '1px solid #d1fae5',
          borderRadius: 8,
          backgroundColor: '#ecfdf5',
          textAlign: 'center',
          fontSize: 13,
          color: '#065f46',
        }}
      >
        Thank you for your feedback!
      </div>
    )
  }

  return (
    <div
      style={{
        marginTop: 20,
        padding: 16,
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        backgroundColor: '#fafafa',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', marginBottom: 10 }}>
        Rate extraction quality
      </div>

      {/* Stars */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => setRating(star)}
            onMouseEnter={() => setHoveredStar(star)}
            onMouseLeave={() => setHoveredStar(0)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              color: star <= (hoveredStar || rating) ? '#f59e0b' : '#d1d5db',
              transition: 'color 0.1s',
            }}
          >
            <Star
              style={{ width: 22, height: 22 }}
              fill={star <= (hoveredStar || rating) ? '#f59e0b' : 'none'}
            />
          </button>
        ))}
      </div>

      {/* Comment */}
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional comment..."
        rows={2}
        style={{
          width: '100%',
          fontSize: 13,
          fontFamily: 'inherit',
          border: '1px solid #d1d5db',
          borderRadius: 6,
          padding: '8px 10px',
          resize: 'vertical',
          outline: 'none',
          boxSizing: 'border-box',
          marginBottom: 10,
        }}
      />

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={rating === 0 || submitting}
        style={{
          padding: '8px 20px',
          fontSize: 13,
          fontWeight: 600,
          fontFamily: 'inherit',
          borderRadius: 6,
          border: 'none',
          backgroundColor: rating === 0 ? '#e5e7eb' : '#191919',
          color: rating === 0 ? '#9ca3af' : '#fff',
          cursor: rating === 0 || submitting ? 'not-allowed' : 'pointer',
        }}
      >
        {submitting ? 'Submitting...' : 'Submit Rating'}
      </button>
    </div>
  )
}

/* ── Tools Tab ── */

function ToolsTab({
  onClone,
  onDelete,
  onAddToLibrary,
  onBuildFromDocument,
  buildingFromDoc,
  hasDocuments,
}: {
  onClone: () => void
  onDelete: () => void
  onAddToLibrary: () => void
  onBuildFromDocument: () => void
  buildingFromDoc: boolean
  hasDocuments: boolean
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
        {/* Add to Library */}
        <ToolCard
          title="Add to Library"
          description="Save this extraction to a library for reuse"
          onClick={onAddToLibrary}
        />
        {/* Delete */}
        <ToolCard
          title="Delete"
          description="Permanently delete this extraction"
          danger
          onClick={onDelete}
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
}: {
  title: string
  description: string
  disabled?: boolean
  danger?: boolean
  onClick: () => void
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
      setState({ sourceIndex: 0, runIndex: 0, phase: '', pct: 0, elapsed: 0 })
      return
    }

    const start = startRef()
    const mode = config.mode ?? 'one_pass'
    const passCount = mode === 'two_pass' ? 2 : 1
    const hasConsensus = config.repetition?.enabled ?? false
    const consensusMultiplier = hasConsensus ? 3 : 1

    // Each source×run = one "step". Each step has sub-phases.
    const totalSteps = numSources * numRuns
    const secsPerStep = passCount * consensusMultiplier * 4 // rough estimate: 4s per LLM call
    const extractionEstSecs = totalSteps * secsPerStep
    // Analysis is now pure normalization (no LLM judge calls), effectively instant
    const analysisEstSecs = 2
    const totalEstSecs = extractionEstSecs + analysisEstSecs

    // Extraction phase gets 0-97%, analysis phase gets 97-99%
    const extractionPctCap = 0.97

    const interval = setInterval(() => {
      const elapsed = (Date.now() - start) / 1000

      // Two-phase progress: extraction then analysis
      const inAnalysisPhase = elapsed > extractionEstSecs * 0.8
      let rawPct: number
      if (!inAnalysisPhase) {
        // Extraction phase: asymptotic up to extractionPctCap
        rawPct = extractionPctCap * (1 - Math.exp(-elapsed / (extractionEstSecs * 0.5)))
      } else {
        // Analysis phase: continue from where extraction left off, creep toward 99%
        const analysisElapsed = elapsed - extractionEstSecs * 0.8
        const baselinePct = extractionPctCap * (1 - Math.exp(-(extractionEstSecs * 0.8) / (extractionEstSecs * 0.5)))
        const remainingPct = 0.99 - baselinePct
        rawPct = baselinePct + remainingPct * (1 - Math.exp(-analysisElapsed / (analysisEstSecs * 0.6)))
      }
      rawPct = Math.min(0.99, rawPct)

      // Map pct to source/run indices (based on extraction phase only)
      const extractionPct = Math.min(rawPct / extractionPctCap, 1)
      const stepProgress = extractionPct * totalSteps
      const currentStep = Math.min(Math.floor(stepProgress), totalSteps - 1)
      const si = Math.floor(currentStep / numRuns)
      const ri = currentStep % numRuns

      // Phase label
      let phase: string
      if (inAnalysisPhase) {
        phase = 'Analyzing accuracy & consistency...'
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

  const currentSource = sources[progress.sourceIndex]
  const sourceLabel = currentSource
    ? (currentSource.document_title || (currentSource.source_type === 'text' ? `Text Chunk ${progress.sourceIndex + 1}` : `Source ${progress.sourceIndex + 1}`))
    : ''

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
            Source {progress.sourceIndex + 1}/{sources.length}: {sourceLabel}
          </div>
          <div style={{ fontSize: 12, color: '#3b5998', marginTop: 2 }}>
            Replicate {progress.runIndex + 1} of {numRuns} — {progress.phase}
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
  items,
  extractionConfig,
}: {
  searchSetUuid: string
  items: { id: string; searchphrase: string }[]
  extractionConfig: ExtractionConfig
}) {
  const { selectedDocUuids, viewDocument } = useWorkspace()
  const [sources, setSources] = useState<SourceLocal[]>([])
  const [loadingSources, setLoadingSources] = useState(true)
  const [numRuns, setNumRuns] = useState(3)
  const [validating, setValidating] = useState(false)
  const [results, setResults] = useState<ValidationV2Result | null>(null)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [qualityHistory, setQualityHistory] = useState<QualityHistoryRun[]>([])
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [fillingSourceId, setFillingSourceId] = useState<string | null>(null)
  const [fillError, setFillError] = useState<string | null>(null)
  const fillAbortRef = useRef<AbortController | null>(null)
  const progress = useValidationProgress(validating, sources.length, numRuns, items.length, extractionConfig)

  // Debounce timers keyed by source id
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  // Load persisted test cases on mount
  useEffect(() => {
    setLoadingSources(true)
    listTestCases(searchSetUuid)
      .then(cases => {
        setSources(cases.map(tc => ({
          id: tc.uuid,
          source_type: tc.source_type as 'document' | 'text',
          document_uuid: tc.document_uuid ?? undefined,
          document_title: tc.label || undefined,
          source_text: tc.source_text ?? undefined,
          expected_values: tc.expected_values,
          expanded: false,
        })))
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

  const addDocuments = async (docs: { uuid: string; title: string }[]) => {
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
    if (!src.document_uuid || fillAbortRef.current) return
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
      const apiSources: ValidationSource[] = sources.map((s, i) => ({
        source_type: s.source_type,
        document_uuid: s.document_uuid,
        label: s.document_title || (s.source_type === 'text' ? `Text Chunk ${i + 1}` : undefined),
        source_text: s.source_text,
        expected_values: s.expected_values,
      }))
      const res = await runValidationV2({
        search_set_uuid: searchSetUuid,
        sources: apiSources,
        num_runs: numRuns,
      })
      setResults(res)
      getExtractionQualityHistory(searchSetUuid)
        .then(r => setQualityHistory(r.runs))
        .catch(() => {})
    } finally {
      setValidating(false)
    }
  }

  const existingUuids = sources.filter(s => s.document_uuid).map(s => s.document_uuid!)

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* 1. Source Management */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 12 }}>
          Validation Sources
        </div>

        {loadingSources ? (
          <div style={{
            textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0',
            border: '1px dashed #d1d5db', borderRadius: 8,
          }}>
            <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', display: 'inline-block' }} /> Loading sources...
          </div>
        ) : sources.length === 0 ? (
          <div style={{
            textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0',
            border: '1px dashed #d1d5db', borderRadius: 8,
          }}>
            Add documents or text to validate against.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {sources.map((src, i) => {
              const label = src.document_title || (src.source_type === 'text' ? `Text Chunk ${i + 1}` : `Document ${i + 1}`)
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
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {items.map(item => (
                          <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{
                              fontSize: 11, color: '#374151', width: 120, flexShrink: 0,
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}>
                              {item.searchphrase}
                            </span>
                            <input
                              value={src.expected_values[item.searchphrase] ?? ''}
                              onChange={e => updateExpectedValue(src.id, item.searchphrase, e.target.value)}
                              placeholder="Expected value"
                              style={{
                                flex: 1, fontSize: 11, fontFamily: 'inherit',
                                border: '1px solid #d1d5db', borderRadius: 4, padding: '3px 6px',
                                outline: 'none',
                              }}
                            />
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

        {/* Quick add selected docs */}
        {selectedDocUuids.length > 0 && (
          <button
            onClick={() => {
              // We don't have titles here, so use UUIDs as labels
              const newDocs = selectedDocUuids
                .filter(uuid => !existingUuids.includes(uuid))
                .map(uuid => ({ uuid, title: `Document ${uuid.slice(0, 8)}...` }))
              if (newDocs.length > 0) addDocuments(newDocs)
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
        </div>

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

      {/* 3. Quality History Chart */}
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
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 60 }}>
            {[...qualityHistory].reverse().map((run, i) => {
              const accPct = run.accuracy != null ? Math.round(run.accuracy * 100) : null
              const consPct = run.consistency != null ? Math.round(run.consistency * 100) : null
              const barHeight = Math.max(4, Math.round(run.score * 0.6))
              const barColor = run.score >= 90 ? '#059669' : run.score >= 70 ? '#d97706' : '#dc2626'
              return (
                <div
                  key={run.uuid}
                  title={`Run ${i + 1}: Score ${Math.round(run.score)}${accPct != null ? ` | Acc ${accPct}%` : ''}${consPct != null ? ` | Cons ${consPct}%` : ''} | ${new Date(run.created_at).toLocaleDateString()}`}
                  style={{
                    flex: 1, maxWidth: 24, height: barHeight,
                    backgroundColor: barColor, borderRadius: 2,
                    opacity: i === [...qualityHistory].length - 1 ? 1 : 0.6,
                    transition: 'height 0.2s',
                    cursor: 'default',
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

          {/* Run comparison table */}
          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse', marginTop: 12 }}>
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
                          {_renderConfigDetails(run.extraction_config)}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 4. Results — Executive Summary */}
      {results && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>Results</div>

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

          {/* 9. LLM Suggestions */}
          {results.aggregate_accuracy !== null && (
            results.aggregate_accuracy < 0.9 || results.aggregate_consistency < 0.9
          ) && (
            <div style={{
              border: '1px solid #fde68a', borderRadius: 8, padding: 16,
              backgroundColor: '#fffbeb',
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
        </div>
      )}

      {/* Document Picker Dialog */}
      {showDocPicker && (
        <DocumentPickerDialog
          onSelect={addDocuments}
          onClose={() => setShowDocPicker(false)}
          excludeUuids={existingUuids}
        />
      )}
    </div>
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
            {onePass.model && <>
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
                  {p1.model && <>
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
                  {p2.model && <>
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

function DocumentPickerDialog({
  onSelect,
  onClose,
  excludeUuids,
}: {
  onSelect: (docs: { uuid: string; title: string }[]) => void
  onClose: () => void
  excludeUuids: string[]
}) {
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ uuid: string; title: string }[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const excludeRef = useCallback((uuid: string) => excludeUuids.includes(uuid), [excludeUuids.join(',')])

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearching(true)
      searchDocuments(query, 30)
        .then(res => {
          setSearchResults(
            res.items
              .filter(d => !excludeRef(d.uuid))
              .map(d => ({ uuid: d.uuid, title: d.title }))
          )
        })
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [query, excludeRef])

  const toggleDoc = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const handleAdd = () => {
    const docs = searchResults.filter(d => selected.has(d.uuid))
    onSelect(docs)
    onClose()
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: '#fff', borderRadius: 12, width: 480, maxHeight: '70vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#202124' }}>Add Documents</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>
        <div style={{ padding: '12px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search documents..."
              style={{
                width: '100%', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px 8px 32px',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 20px', minHeight: 200, maxHeight: 400 }}>
          {searching ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
              <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite', display: 'inline-block' }} />
            </div>
          ) : searchResults.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
              {query ? 'No documents found.' : 'Type to search documents...'}
            </div>
          ) : (
            searchResults.map(doc => (
              <label key={doc.uuid} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0',
                borderBottom: '1px solid #f0f0f0', cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={selected.has(doc.uuid)}
                  onChange={() => toggleDoc(doc.uuid)}
                />
                <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                <span style={{ fontSize: 13, color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.title}
                </span>
              </label>
            ))
          )}
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid #e5e7eb', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
              color: '#374151', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={selected.size === 0}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 6, border: 'none',
              backgroundColor: selected.size > 0 ? '#191919' : '#e5e7eb',
              color: selected.size > 0 ? '#fff' : '#9ca3af',
              cursor: selected.size > 0 ? 'pointer' : 'not-allowed',
            }}
          >
            Add {selected.size > 0 ? `${selected.size} ` : ''}Selected
          </button>
        </div>
      </div>
    </div>
  )
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
