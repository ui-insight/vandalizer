import { useCallback, useEffect, useState } from 'react'
import { X, Pencil, Loader2, Copy, Trash2, Star } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useSearchSetItems } from '../../hooks/useExtractions'
import {
  getSearchSet,
  updateSearchSet,
  cloneSearchSet,
  deleteSearchSet,
  runExtractionSync,
} from '../../api/extractions'
import { getModels } from '../../api/config'
import { submitRating } from '../../api/feedback'
import { useLibraries } from '../../hooks/useLibrary'
import { useTeams } from '../../hooks/useTeams'
import { AddToLibraryDialog } from '../library/AddToLibraryDialog'
import type { SearchSet, ModelInfo } from '../../types/workflow'

type Tab = 'design' | 'tools' | 'advanced'

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
  const { openExtractionId, closeExtraction, selectedDocUuids } = useWorkspace()
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

  const { items, loading: itemsLoading, refresh: refreshItems, add, remove } =
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
          padding: '0 24px',
          backgroundColor: '#fff',
          flexShrink: 0,
        }}
      >
        {(['design', 'tools', 'advanced'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 16px',
              fontSize: 13,
              fontWeight: 600,
              fontFamily: 'inherit',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #000' : '2px solid transparent',
              color: activeTab === tab ? '#000' : '#6b7280',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {activeTab === 'design' && (
          <DesignTab
            items={items}
            itemsLoading={itemsLoading}
            results={results}
            hasResults={hasResults}
            onExport={handleExport}
            onRemoveItem={remove}
            pdfTitle={searchSet?.title ?? ''}
            searchSetUuid={openExtractionId ?? undefined}
          />
        )}
        {activeTab === 'tools' && (
          <ToolsTab
            onClone={handleClone}
            onDelete={handleDelete}
            onAddToLibrary={() => setShowAddToLibrary(true)}
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

function DesignTab({
  items,
  itemsLoading,
  results,
  hasResults,
  onExport,
  onRemoveItem,
  pdfTitle,
  searchSetUuid,
}: {
  items: { id: string; searchphrase: string }[]
  itemsLoading: boolean
  results: Record<string, string>
  hasResults: boolean
  onExport: () => void
  onRemoveItem: (id: string) => void
  pdfTitle: string
  searchSetUuid?: string
}) {
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
            return (
              <div
                key={item.id}
                style={{
                  padding: '10px 0',
                  borderBottom: '1px solid #f0f0f0',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: '#9ca3af',
                      width: 24,
                      textAlign: 'right',
                      flexShrink: 0,
                    }}
                  >
                    {idx + 1}
                  </span>
                  <span style={{ fontSize: 14, color: '#202124', flex: 1 }}>
                    {item.searchphrase}
                  </span>
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
                    style={{
                      marginLeft: 45,
                      marginTop: 4,
                      fontSize: 13,
                      fontWeight: 600,
                      color: '#202124',
                    }}
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
}: {
  onClone: () => void
  onDelete: () => void
  onAddToLibrary: () => void
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
          title="From Document"
          description="Build extraction from a selected document using AI"
          onClick={() => {
            alert('AI-powered field generation from documents is coming soon. For now, add fields manually in the Fields tab.')
          }}
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
              <option key={m.name} value={m.name}>
                {m.tag || m.name}{m.external ? ' (External)' : ''}
              </option>
            ))}
          </select>
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
