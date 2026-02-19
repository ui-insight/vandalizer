import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useLibraries, useLibraryItems } from '../../hooks/useLibrary'
import { LibraryItemRow } from '../library/LibraryItemRow'
import { cloneToPersonal, shareToTeam, addItem as addItemToLibrary } from '../../api/library'
import { createWorkflow } from '../../api/workflows'
import { createSearchSet } from '../../api/extractions'
import {
  Search,
  Layers,
  Star,
  Pin,
  Plus,
  Workflow,
  Filter,
  Terminal,
  Code,
} from 'lucide-react'

type ScopeTab = 'mine' | 'team' | 'explore'
type ViewFilter = 'all' | 'favorites' | 'pinned'
type KindFilter = 'all' | 'workflow' | 'search_set'
type SortOption = 'recent' | 'az'

export function LibraryTab() {
  const { openWorkflow, openExtraction, sendChatMessage } = useWorkspace()
  const { user } = useAuth()
  const teamId = user?.current_team ?? undefined
  const { libraries, loading: libLoading, error, refresh } = useLibraries(teamId)

  const [scope, setScope] = useState<ScopeTab>('mine')
  const [search, setSearch] = useState('')
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all')
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [sortOption, setSortOption] = useState<SortOption>('recent')
  const [newMenuOpen, setNewMenuOpen] = useState(false)
  const newMenuRef = useRef<HTMLDivElement>(null)

  // Close + New menu on outside click
  useEffect(() => {
    if (!newMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (newMenuRef.current && !newMenuRef.current.contains(e.target as Node)) {
        setNewMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [newMenuOpen])

  // Find the library matching current scope
  const activeLibrary =
    scope === 'mine'
      ? libraries.find((l) => l.scope === 'personal') ?? null
      : scope === 'team'
        ? libraries.find((l) => l.scope === 'team') ?? null
        : libraries.find((l) => l.scope === 'verified') ?? null

  // Items
  const { items, loading: itemsLoading, refresh: refreshItems, update, remove } = useLibraryItems(
    activeLibrary?.id ?? null,
    {
      kind: kindFilter === 'all' ? undefined : kindFilter,
      search: search || undefined,
    },
  )

  // Actions
  const handlePin = async (itemId: string, pinned: boolean) => {
    await update(itemId, { pinned })
  }
  const handleFavorite = async (itemId: string, favorited: boolean) => {
    await update(itemId, { favorited })
  }
  const handleClone = async (itemId: string) => {
    await cloneToPersonal(itemId)
    refreshItems()
  }
  const handleShare = async (itemId: string) => {
    if (!teamId) return
    await shareToTeam(itemId, teamId)
    refreshItems()
  }
  const handleRemove = async (itemId: string) => {
    await remove(itemId)
  }

  // Apply view filter + sort
  const filtered = items.filter((item) => {
    if (viewFilter === 'favorites') return item.favorited
    if (viewFilter === 'pinned') return item.pinned
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortOption === 'az') return a.name.localeCompare(b.name)
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    if (a.favorited !== b.favorited) return a.favorited ? -1 : 1
    return 0
  })

  // Creation modal state
  type ModalType = 'workflow' | 'extraction' | 'prompt' | 'formatter' | null
  const [createModalType, setCreateModalType] = useState<ModalType>(null)
  const [createName, setCreateName] = useState('')
  const [createDesc, setCreateDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const openCreateModal = (type: NonNullable<ModalType>) => {
    setCreateModalType(type)
    setCreateName('')
    setCreateDesc('')
    setCreateError(null)
  }

  const closeCreateModal = () => {
    setCreateModalType(null)
    setCreateName('')
    setCreateDesc('')
    setCreateError(null)
  }

  const handleCreate = async () => {
    if (!createName.trim()) return
    setCreating(true)
    setCreateError(null)
    const personalLib = libraries.find((l) => l.scope === 'personal')
    try {
      if (createModalType === 'workflow') {
        const wf = await createWorkflow({ name: createName.trim(), description: createDesc.trim() || undefined })
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: wf.id, kind: 'workflow' })
        }
        closeCreateModal()
        refreshItems()
        openWorkflow(wf.id)
      } else {
        // extraction, prompt, or formatter — all stored as SearchSets
        const config = createDesc.trim() ? { content: createDesc.trim() } : undefined
        const ss = await createSearchSet({ title: createName.trim(), space: 'default', set_type: createModalType ?? 'extraction', extraction_config: config })
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: ss.id, kind: 'search_set' })
        }
        closeCreateModal()
        refreshItems()
        if (createModalType === 'extraction') {
          openExtraction(ss.uuid)
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      console.error('Failed to create item:', e)
      setCreateError(msg)
    } finally {
      setCreating(false)
    }
  }

  // Modal config per type
  const modalConfig: Record<NonNullable<ModalType>, { title: string; namePlaceholder: string; showDesc: boolean; descPlaceholder: string }> = {
    workflow: {
      title: 'Start a workflow',
      namePlaceholder: 'Name your workflow',
      showDesc: true,
      descPlaceholder: "A one sentence description of the workflow's purpose.",
    },
    extraction: {
      title: 'Name the task',
      namePlaceholder: 'Name your extraction task',
      showDesc: false,
      descPlaceholder: '',
    },
    prompt: {
      title: 'Prompt creation',
      namePlaceholder: 'Title your prompt',
      showDesc: true,
      descPlaceholder: 'Write your prompt here',
    },
    formatter: {
      title: 'Formatter creation',
      namePlaceholder: 'Title your formatter',
      showDesc: true,
      descPlaceholder: 'Write your formatting instructions here',
    },
  }

  if (libLoading) {
    return (
      <div className="flex items-center justify-center h-full" style={{ fontSize: 13, color: '#888' }}>
        Loading...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 gap-3" style={{ fontSize: 13, color: '#888' }}>
        <p>{error}</p>
        <button
          onClick={refresh}
          style={{
            borderRadius: 'var(--ui-radius, 12px)',
            background: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            padding: '6px 12px',
            fontSize: 13,
            fontWeight: 700,
            border: 'none',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div
      className="flex flex-col h-full"
      style={{
        position: 'relative',
        backgroundColor: '#fff',
        ['--library-highlight' as string]: 'var(--highlight-color, #eab308)',
        ['--library-highlight-ink' as string]: 'color-mix(in srgb, var(--library-highlight) 65%, #1f2937)',
        ['--library-highlight-soft' as string]: 'color-mix(in srgb, var(--library-highlight) 18%, #ffffff)',
        ['--library-highlight-muted' as string]: 'color-mix(in srgb, var(--library-highlight) 10%, #f8f9fa)',
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          flexShrink: 0,
          borderBottom: '1px solid #e0e0e0',
          backgroundColor: '#fff',
          padding: '14px 24px 6px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        {/* Row 1: Title + Search + New */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', color: '#202124', whiteSpace: 'nowrap' }}>
            Library
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, justifyContent: 'flex-end', minWidth: 0 }}>
            {/* Search */}
            <div style={{ position: 'relative', flex: 1, maxWidth: 400, minWidth: 0 }}>
              <Search
                style={{
                  position: 'absolute',
                  left: 12,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: 16,
                  height: 16,
                  color: '#5f6368',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search..."
                style={{
                  width: '100%',
                  background: '#f1f3f4',
                  border: '1px solid transparent',
                  borderRadius: 8,
                  padding: '8px 16px 8px 38px',
                  fontSize: 14,
                  outline: 'none',
                  transition: 'all 0.2s',
                  fontFamily: 'inherit',
                }}
                onFocus={(e) => {
                  e.currentTarget.style.background = '#fff'
                  e.currentTarget.style.borderColor = '#dadce0'
                  e.currentTarget.style.boxShadow = '0 1px 2px rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.background = '#f1f3f4'
                  e.currentTarget.style.borderColor = 'transparent'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>

            {/* + New button with dropdown */}
            <div ref={newMenuRef} style={{ position: 'relative', flexShrink: 0 }}>
              <button
                onClick={() => setNewMenuOpen(!newMenuOpen)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  borderRadius: 30,
                  backgroundColor: '#2980b9',
                  border: '2px solid #2980b9',
                  padding: '6px 14px',
                  fontSize: 13,
                  fontWeight: 700,
                  color: '#fff',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'filter 0.15s',
                }}
              >
                <Plus style={{ width: 14, height: 14 }} />
                New
              </button>

              {newMenuOpen && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 6px)',
                    zIndex: 1000,
                    minWidth: 220,
                    borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid rgba(0,0,0,0.14)',
                    background: '#fff',
                    boxShadow: '0 10px 28px rgba(0,0,0,0.16)',
                    padding: 6,
                  }}
                >
                  <NewMenuItem icon={<Workflow style={{ width: 18, height: 18 }} />} label="New Workflow" onClick={() => { setNewMenuOpen(false); openCreateModal('workflow') }} />
                  <NewMenuItem icon={<Filter style={{ width: 18, height: 18 }} />} label="New Extraction" onClick={() => { setNewMenuOpen(false); openCreateModal('extraction') }} />
                  <NewMenuItem icon={<Terminal style={{ width: 18, height: 18 }} />} label="New Prompt" onClick={() => { setNewMenuOpen(false); openCreateModal('prompt') }} />
                  <NewMenuItem icon={<Code style={{ width: 18, height: 18 }} />} label="New Formatter" onClick={() => { setNewMenuOpen(false); openCreateModal('formatter') }} />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 2: Scope tabs */}
        <div style={{ display: 'flex', gap: 0, marginTop: 2, marginBottom: 10 }}>
          {([
            { key: 'mine' as const, label: 'Mine' },
            { key: 'team' as const, label: 'Team' },
            { key: 'explore' as const, label: 'Explore' },
          ]).map(({ key, label }) => {
            const active = scope === key
            return (
              <button
                key={key}
                onClick={() => {
                  setScope(key)
                  setViewFilter('all')
                }}
                style={{
                  padding: '0 14px',
                  fontWeight: 500,
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 0,
                  lineHeight: '1.2',
                  minHeight: 34,
                  background: 'none',
                  border: 'none',
                  borderBottom: active ? '2px solid var(--library-highlight, #eab308)' : '2px solid transparent',
                  color: active ? 'var(--library-highlight, #eab308)' : '#5f6368',
                  cursor: 'pointer',
                  transition: 'color 0.15s',
                  whiteSpace: 'nowrap',
                }}
              >
                {label}
              </button>
            )
          })}
        </div>

        {/* Row 3: Filter chips + sort */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, paddingBottom: 2 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {([
              { value: 'all' as const, label: 'All Types' },
              { value: 'workflow' as const, label: 'Workflows' },
              { value: 'search_set' as const, label: 'Tasks' },
            ]).map(({ value, label }) => {
              const active = kindFilter === value
              return (
                <button
                  key={value}
                  onClick={() => setKindFilter(value)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    height: 32,
                    padding: '0 12px',
                    borderRadius: 16,
                    border: active ? '1px solid var(--library-highlight-soft)' : '1px solid #dadce0',
                    backgroundColor: active ? 'var(--library-highlight-soft)' : '#fff',
                    fontSize: 13,
                    fontFamily: 'inherit',
                    color: active ? 'var(--library-highlight-ink)' : '#3c4043',
                    cursor: 'pointer',
                    userSelect: 'none',
                    transition: 'all 0.15s',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'flex-end', minWidth: 150 }}>
            <select
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value as SortOption)}
              style={{
                borderRadius: 999,
                fontSize: 13,
                fontFamily: 'inherit',
                padding: '0 32px 0 12px',
                height: 32,
                border: '1px solid #dadce0',
                background: '#fff',
                color: '#3c4043',
                cursor: 'pointer',
              }}
            >
              <option value="recent">Recently Used</option>
              <option value="az">A-Z</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Body: sidebar + results ── */}
      <div style={{ display: 'flex', flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
        {/* Sidebar */}
        <div
          style={{
            width: 180,
            flexShrink: 0,
            minHeight: 0,
            borderRight: '1px solid #f0f0f0',
            backgroundColor: '#fafafa',
            padding: '20px 0',
            overflowY: 'auto',
          }}
        >
          <div
            style={{
              padding: '0 24px',
              marginBottom: 8,
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#888',
              letterSpacing: '0.5px',
            }}
          >
            Saved Views
          </div>

          {([
            { view: 'all' as const, icon: Layers, label: 'All Items' },
            { view: 'favorites' as const, icon: Star, label: 'Favorites' },
            { view: 'pinned' as const, icon: Pin, label: 'Pinned' },
          ]).map(({ view, icon: Icon, label }) => {
            const isActive = viewFilter === view
            const count =
              view === 'favorites'
                ? items.filter((i) => i.favorited).length
                : view === 'pinned'
                  ? items.filter((i) => i.pinned).length
                  : 0
            return (
              <div
                key={view}
                onClick={() => setViewFilter(view)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '10px 16px 10px 24px',
                  cursor: 'pointer',
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                  backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                  borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                  transition: 'background 0.1s',
                }}
              >
                <Icon style={{ width: 14, height: 14, marginRight: 10, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{label}</span>
                {count > 0 && (
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: '#aaa', fontWeight: 400 }}>{count}</span>
                )}
              </div>
            )
          })}
        </div>

        {/* Results pane */}
        <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', backgroundColor: '#fff', borderRight: '1px solid #f0f0f0' }}>
          {/* List header */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '4fr 2fr 150px',
              padding: '10px 24px',
              backgroundColor: '#fff',
              borderBottom: '1px solid #f0f0f0',
              fontSize: 12,
              fontWeight: 500,
              color: '#5f6368',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            <div>Name</div>
            <div>Last Used</div>
            <div style={{ textAlign: 'right' }}>Actions</div>
          </div>

          {/* Items list */}
          <div style={{ flexGrow: 1, overflowY: 'auto', minHeight: 0, padding: 0 }}>
            {itemsLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#888', fontSize: 13 }}>Loading...</div>
            ) : sorted.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#888', fontSize: 13 }}>No items found.</div>
            ) : (
              sorted.map((item) => (
                <LibraryItemRow
                  key={item.id}
                  item={item}
                  scope={scope === 'explore' ? 'team' : scope}
                  onPin={handlePin}
                  onFavorite={handleFavorite}
                  onClone={handleClone}
                  onShare={handleShare}
                  onRemove={handleRemove}
                  onOpen={(it) => {
                    if (it.kind === 'workflow') {
                      openWorkflow(it.item_id)
                    } else if (it.set_type === 'prompt' || it.set_type === 'formatter') {
                      const content = it.description || it.name
                      sendChatMessage(content)
                    } else if (it.set_type === 'extraction' && it.item_uuid) {
                      openExtraction(it.item_uuid)
                    }
                  }}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* Creation Modal (workflow / extraction / prompt / formatter) */}
      {createModalType && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 2000,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            paddingTop: '8%',
            backgroundColor: 'rgba(0,0,0,0.4)',
          }}
          onClick={closeCreateModal}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#fff',
              borderRadius: 'var(--ui-radius, 12px)',
              padding: '28px 32px',
              width: '90%',
              maxWidth: 480,
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }}
          >
            <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 600, color: '#202124', textAlign: 'left' }}>
              {modalConfig[createModalType].title}
            </h2>
            <div style={{ marginBottom: 16 }}>
              <input
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder={modalConfig[createModalType].namePlaceholder}
                autoFocus
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  border: '1px solid #dadce0',
                  borderRadius: 8,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
                onKeyDown={(e) => e.key === 'Enter' && !modalConfig[createModalType].showDesc && handleCreate()}
              />
            </div>
            {modalConfig[createModalType].showDesc && (
              <div style={{ marginBottom: 20 }}>
                <textarea
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  placeholder={modalConfig[createModalType].descPlaceholder}
                  rows={createModalType === 'workflow' ? 5 : 10}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: 14,
                    fontFamily: 'inherit',
                    border: '1px solid #dadce0',
                    borderRadius: 8,
                    outline: 'none',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            )}
            {createError && (
              <div style={{ marginBottom: 12, padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: '#dc2626' }}>
                {createError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleCreate}
                disabled={creating || !createName.trim()}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  cursor: creating || !createName.trim() ? 'not-allowed' : 'pointer',
                  opacity: creating || !createName.trim() ? 0.5 : 1,
                }}
              >
                {creating ? 'Creating...' : createModalType === 'workflow' ? 'Create Workflow' : 'Create Task'}
              </button>
              <button
                onClick={closeCreateModal}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: '1px solid #dadce0',
                  backgroundColor: '#fff',
                  color: '#5f6368',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function NewMenuItem({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        width: '100%',
        alignItems: 'center',
        gap: 10,
        borderRadius: 8,
        padding: '10px 12px',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 14,
        color: '#1f2937',
        textAlign: 'left',
        minHeight: 40,
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
    >
      <span style={{ width: 18, display: 'flex', justifyContent: 'center', flexShrink: 0, color: '#5f6368' }}>{icon}</span>
      {label}
    </button>
  )
}
