import { useCallback, useEffect, useState } from 'react'
import { X, Pencil, Loader2, Copy, Trash2, Star, GripVertical, Plus, ChevronDown, ChevronRight, Play, TrendingUp, Sparkles } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useSearchSetItems } from '../../hooks/useExtractions'
import {
  getSearchSet,
  updateSearchSet,
  cloneSearchSet,
  deleteSearchSet,
  runExtractionSync,
  buildFromDocument,
  listTestCases,
  createTestCase,
  updateTestCase,
  deleteTestCase,
  runValidation,
  getExtractionQualityHistory,
  getExtractionImprovementSuggestions,
} from '../../api/extractions'
import type { TestCase, ValidationResult, QualityHistoryRun } from '../../api/extractions'
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

/* ── Validate Tab ── */

function ValidateTab({
  searchSetUuid,
  items,
}: {
  searchSetUuid: string
  items: { id: string; searchphrase: string }[]
}) {
  const [testCases, setTestCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(true)
  const [numRuns, setNumRuns] = useState(3)
  const [validating, setValidating] = useState(false)
  const [results, setResults] = useState<ValidationResult | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [expandedCase, setExpandedCase] = useState<string | null>(null)
  const [editingCase, setEditingCase] = useState<string | null>(null)
  const [qualityHistory, setQualityHistory] = useState<QualityHistoryRun[]>([])
  const [suggestions, setSuggestions] = useState<string | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)

  const loadTestCases = useCallback(async () => {
    setLoading(true)
    try {
      const tcs = await listTestCases(searchSetUuid)
      setTestCases(tcs)
    } finally {
      setLoading(false)
    }
  }, [searchSetUuid])

  useEffect(() => {
    loadTestCases()
  }, [loadTestCases])

  useEffect(() => {
    getExtractionQualityHistory(searchSetUuid)
      .then(r => setQualityHistory(r.runs))
      .catch(() => {})
  }, [searchSetUuid])

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

  const handleDelete = async (uuid: string) => {
    await deleteTestCase(uuid)
    setTestCases(prev => prev.filter(tc => tc.uuid !== uuid))
  }

  const handleRunValidation = async () => {
    setValidating(true)
    setSuggestions(null)
    try {
      const res = await runValidation({
        search_set_uuid: searchSetUuid,
        num_runs: numRuns,
      })
      setResults(res)
      // Refresh quality history after new validation run
      getExtractionQualityHistory(searchSetUuid)
        .then(r => setQualityHistory(r.runs))
        .catch(() => {})
    } finally {
      setValidating(false)
    }
  }

  const handleSaveTestCase = async (data: {
    label: string
    source_type: string
    source_text?: string
    document_uuid?: string
    expected_values: Record<string, string>
  }) => {
    if (editingCase) {
      await updateTestCase(editingCase, data)
    } else {
      await createTestCase({ search_set_uuid: searchSetUuid, ...data })
    }
    setShowCreateForm(false)
    setEditingCase(null)
    loadTestCases()
  }

  const startEdit = (tc: TestCase) => {
    setEditingCase(tc.uuid)
    setShowCreateForm(true)
  }

  const editingTestCase = editingCase ? testCases.find(tc => tc.uuid === editingCase) : undefined

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Test Cases Section */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>Test Cases</div>
          <button
            onClick={() => { setEditingCase(null); setShowCreateForm(true) }}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
              color: '#202124', cursor: 'pointer',
            }}
          >
            <Plus style={{ width: 12, height: 12 }} /> Add Test Case
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '16px 0' }}>Loading...</div>
        ) : testCases.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0', border: '1px dashed #d1d5db', borderRadius: 8 }}>
            No test cases yet. Add one to start validating.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {testCases.map(tc => {
              const expectedCount = Object.values(tc.expected_values).filter(v => v).length
              return (
                <div key={tc.uuid} style={{ padding: '10px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 14, color: '#202124', flex: 1 }}>{tc.label}</span>
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 4,
                      backgroundColor: tc.source_type === 'text' ? '#eff6ff' : '#fef3c7',
                      color: tc.source_type === 'text' ? '#1d4ed8' : '#92400e',
                    }}>
                      {tc.source_type}
                    </span>
                    <span style={{ fontSize: 11, color: '#5f6368' }}>
                      {expectedCount} of {items.length} fields
                    </span>
                    <button
                      onClick={() => startEdit(tc)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                    >
                      <Pencil style={{ width: 12, height: 12 }} />
                    </button>
                    <button
                      onClick={() => handleDelete(tc.uuid)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#9ca3af', display: 'flex' }}
                    >
                      <Trash2 style={{ width: 12, height: 12 }} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Create/Edit Form */}
      {showCreateForm && (
        <TestCaseForm
          items={items}
          initial={editingTestCase}
          onSave={handleSaveTestCase}
          onCancel={() => { setShowCreateForm(false); setEditingCase(null) }}
        />
      )}

      {/* Run Controls */}
      {!showCreateForm && testCases.length > 0 && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 12 }}>Run Validation</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <label style={{ fontSize: 13, color: '#5f6368' }}>Runs:</label>
            <input
              type="number"
              min={1}
              max={5}
              value={numRuns}
              onChange={e => setNumRuns(Math.min(5, Math.max(1, parseInt(e.target.value) || 1)))}
              style={{
                width: 50, fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, padding: '6px 8px',
              }}
            />
            <button
              onClick={handleRunValidation}
              disabled={validating}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                borderRadius: 8, border: 'none',
                backgroundColor: '#191919', color: '#fff',
                cursor: validating ? 'not-allowed' : 'pointer',
                opacity: validating ? 0.5 : 1,
              }}
            >
              {validating ? (
                <><Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> Validating...</>
              ) : (
                <><Play style={{ width: 14, height: 14 }} /> Run Validation</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Quality History Chart — visible even before running validation */}
      {!showCreateForm && qualityHistory.length > 1 && (
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
        </div>
      )}

      {/* Results */}
      {results && !showCreateForm && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
          {/* Aggregate banner */}
          <div style={{
            display: 'flex', gap: 16, padding: '12px 16px', marginBottom: 16,
            borderRadius: 8, backgroundColor: '#f9fafb', border: '1px solid #e5e7eb',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Accuracy</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: _scoreColor(results.aggregate_accuracy) }}>
                {results.aggregate_accuracy !== null ? `${Math.round(results.aggregate_accuracy * 100)}%` : 'N/A'}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Consistency</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: _scoreColor(results.aggregate_consistency) }}>
                {Math.round(results.aggregate_consistency * 100)}%
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: '#5f6368', marginBottom: 2 }}>Runs</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#202124' }}>{results.num_runs}</div>
            </div>
          </div>

          {/* LLM Improvement Suggestions — show when below A grade (score < 90) */}
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

          {/* Per-test-case results */}
          {results.test_cases.map(tcr => (
            <div key={tcr.test_case_uuid} style={{ marginBottom: 8, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
              <button
                onClick={() => setExpandedCase(expandedCase === tcr.test_case_uuid ? null : tcr.test_case_uuid)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '10px 14px', border: 'none', backgroundColor: '#fafafa',
                  cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                }}
              >
                {expandedCase === tcr.test_case_uuid
                  ? <ChevronDown style={{ width: 14, height: 14, color: '#5f6368', flexShrink: 0 }} />
                  : <ChevronRight style={{ width: 14, height: 14, color: '#5f6368', flexShrink: 0 }} />
                }
                <span style={{ fontSize: 13, fontWeight: 600, color: '#202124', flex: 1 }}>{tcr.label}</span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, backgroundColor: _scoreBg(tcr.overall_accuracy), color: _scoreColor(tcr.overall_accuracy) }}>
                  {tcr.overall_accuracy !== null ? `${Math.round(tcr.overall_accuracy * 100)}% acc` : 'N/A'}
                </span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, backgroundColor: _scoreBg(tcr.overall_consistency), color: _scoreColor(tcr.overall_consistency) }}>
                  {Math.round(tcr.overall_consistency * 100)}% cons
                </span>
              </button>

              {expandedCase === tcr.test_case_uuid && (
                <div style={{ padding: '0 14px 14px' }}>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginTop: 8 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Field</th>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Expected</th>
                        <th style={{ textAlign: 'left', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Extracted</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Consistency</th>
                        <th style={{ textAlign: 'center', padding: '6px 4px', color: '#5f6368', fontWeight: 600 }}>Accuracy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tcr.fields.map(f => (
                        <tr key={f.field_name} style={{ borderBottom: '1px solid #f0f0f0' }}>
                          <td style={{ padding: '6px 4px', color: '#202124', fontWeight: 500 }}>{f.field_name}</td>
                          <td style={{ padding: '6px 4px', color: '#5f6368' }}>{f.expected ?? '-'}</td>
                          <td style={{ padding: '6px 4px', color: '#202124', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {f.most_common_value ?? 'null'}
                          </td>
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
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
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

function TestCaseForm({
  items,
  initial,
  onSave,
  onCancel,
}: {
  items: { id: string; searchphrase: string }[]
  initial?: TestCase
  onSave: (data: {
    label: string
    source_type: string
    source_text?: string
    document_uuid?: string
    expected_values: Record<string, string>
  }) => void
  onCancel: () => void
}) {
  const [label, setLabel] = useState(initial?.label ?? '')
  const [sourceType, setSourceType] = useState<string>(initial?.source_type ?? 'text')
  const [sourceText, setSourceText] = useState(initial?.source_text ?? '')
  const [documentUuid, setDocumentUuid] = useState(initial?.document_uuid ?? '')
  const [expectedValues, setExpectedValues] = useState<Record<string, string>>(
    initial?.expected_values ?? {}
  )

  const handleSubmit = () => {
    if (!label.trim()) return
    onSave({
      label: label.trim(),
      source_type: sourceType,
      source_text: sourceType === 'text' ? sourceText : undefined,
      document_uuid: sourceType === 'document' ? documentUuid : undefined,
      expected_values: expectedValues,
    })
  }

  return (
    <div style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: 16, backgroundColor: '#fafafa' }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 12 }}>
        {initial ? 'Edit Test Case' : 'New Test Case'}
      </div>

      {/* Label */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#5f6368', display: 'block', marginBottom: 4 }}>Label</label>
        <input
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="e.g. Invoice sample 1"
          style={{
            width: '100%', fontSize: 13, fontFamily: 'inherit',
            border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px',
            outline: 'none', boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Source type toggle */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#5f6368', display: 'block', marginBottom: 4 }}>Source</label>
        <div style={{ display: 'flex', gap: 0, border: '1px solid #d1d5db', borderRadius: 6, overflow: 'hidden', width: 'fit-content' }}>
          {(['text', 'document'] as const).map(st => (
            <button
              key={st}
              onClick={() => setSourceType(st)}
              style={{
                padding: '6px 16px', fontSize: 12, fontWeight: sourceType === st ? 600 : 400,
                fontFamily: 'inherit', border: 'none',
                backgroundColor: sourceType === st ? '#191919' : '#fff',
                color: sourceType === st ? '#fff' : '#202124',
                cursor: 'pointer', textTransform: 'capitalize',
              }}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Source input */}
      {sourceType === 'text' ? (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, fontWeight: 500, color: '#5f6368', display: 'block', marginBottom: 4 }}>Source Text</label>
          <textarea
            value={sourceText}
            onChange={e => setSourceText(e.target.value)}
            placeholder="Paste the text to extract from..."
            rows={4}
            style={{
              width: '100%', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px',
              resize: 'vertical', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>
      ) : (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, fontWeight: 500, color: '#5f6368', display: 'block', marginBottom: 4 }}>Document UUID</label>
          <input
            value={documentUuid}
            onChange={e => setDocumentUuid(e.target.value)}
            placeholder="Paste a document UUID"
            style={{
              width: '100%', fontSize: 13, fontFamily: 'inherit',
              border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px',
              outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>
      )}

      {/* Expected values */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#5f6368', display: 'block', marginBottom: 6 }}>
          Expected Values <span style={{ fontWeight: 400 }}>(leave blank to skip accuracy check)</span>
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map(item => (
            <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: '#374151', width: 140, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.searchphrase}
              </span>
              <input
                value={expectedValues[item.searchphrase] ?? ''}
                onChange={e => setExpectedValues(prev => ({
                  ...prev,
                  [item.searchphrase]: e.target.value,
                }))}
                placeholder="Expected value"
                style={{
                  flex: 1, fontSize: 12, fontFamily: 'inherit',
                  border: '1px solid #d1d5db', borderRadius: 4, padding: '4px 8px',
                  outline: 'none',
                }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button
          onClick={onCancel}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
            borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
            color: '#374151', cursor: 'pointer',
          }}
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={!label.trim()}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
            borderRadius: 6, border: 'none',
            backgroundColor: label.trim() ? '#191919' : '#e5e7eb',
            color: label.trim() ? '#fff' : '#9ca3af',
            cursor: label.trim() ? 'pointer' : 'not-allowed',
          }}
        >
          {initial ? 'Update' : 'Save'}
        </button>
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
