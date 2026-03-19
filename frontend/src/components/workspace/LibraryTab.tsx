import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../../hooks/useAuth'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useLibraries, useLibraryItems } from '../../hooks/useLibrary'
import { LibraryItemRow } from '../library/LibraryItemRow'
import { cloneToPersonal, shareToTeam, addItem as addItemToLibrary, touchItem, listCollections } from '../../api/library'
import { createWorkflow } from '../../api/workflows'
import { createSearchSet, listItems as listSearchSetItems, updateSearchSet, updateItem as updateSearchSetItem } from '../../api/extractions'
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
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
  X,
} from 'lucide-react'
import type { VerifiedCollection } from '../../types/library'
import { useLibraryFolders } from '../../hooks/useLibrary'

type ScopeTab = 'mine' | 'team' | 'explore'
type ViewFilter = 'all' | 'favorites' | 'pinned' | string  // string allows folder UUIDs
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

  // Folder system
  const folderScope = scope === 'team' ? 'team' : 'personal'
  const { folders, refresh: refreshFolders, create: createFolder, rename: renameFolder, remove: removeFolder, moveItems: moveFolderItems } = useLibraryFolders(folderScope, teamId)
  const [folderMenuOpen, setFolderMenuOpen] = useState<string | null>(null)
  const [folderMenuPos, setFolderMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 }) // folder uuid with open menu
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [newFolderMode, setNewFolderMode] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const folderMenuRef = useRef<HTMLDivElement>(null)

  // Collections (Explore tab)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])

  // Fetch collections when Explore tab is active
  useEffect(() => {
    if (scope !== 'explore') { setCollections([]); return }
    listCollections()
      .then(data => setCollections(data.collections))
      .catch(() => {})
  }, [scope])

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

  // Close folder context menu on outside click
  useEffect(() => {
    if (!folderMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (folderMenuRef.current && !folderMenuRef.current.contains(e.target as Node)) {
        setFolderMenuOpen(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [folderMenuOpen])

  // Reset folder view when scope changes
  useEffect(() => {
    if (viewFilter !== 'all' && viewFilter !== 'favorites' && viewFilter !== 'pinned') {
      setViewFilter('all')
    }
    setFolderMenuOpen(null)
    setRenamingFolder(null)
    setNewFolderMode(false)
  }, [scope])

  // Find the library matching current scope
  const activeLibrary =
    scope === 'mine'
      ? libraries.find((l) => l.scope === 'personal') ?? null
      : scope === 'team'
        ? libraries.find((l) => l.scope === 'team') ?? null
        : libraries.find((l) => l.scope === 'verified') ?? null

  // Items — pass folder filter when a folder is selected
  const isCollectionFilter = viewFilter.startsWith('collection:')
  const selectedFolder = viewFilter !== 'all' && viewFilter !== 'favorites' && viewFilter !== 'pinned' && !isCollectionFilter ? viewFilter : undefined
  const { items, loading: itemsLoading, refresh: refreshItems, update, remove } = useLibraryItems(
    activeLibrary?.id ?? null,
    {
      kind: kindFilter === 'all' ? undefined : kindFilter,
      search: search || undefined,
      folder: selectedFolder,
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
  const handleMoveToFolder = async (itemId: string, folderUuid: string | null) => {
    await moveFolderItems([itemId], folderUuid)
    refreshItems()
    refreshFolders()
  }

  // Apply view filter + sort (folder filtering is handled server-side via useLibraryItems)
  const selectedCollection = isCollectionFilter
    ? collections.find(c => viewFilter === `collection:${c.id}`)
    : null
  const collectionItemIds = selectedCollection ? new Set(selectedCollection.item_ids) : null

  const filtered = items.filter((item) => {
    if (viewFilter === 'favorites') return item.favorited
    if (viewFilter === 'pinned') return item.pinned
    if (collectionItemIds) return collectionItemIds.has(item.item_id)
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortOption === 'az') return a.name.localeCompare(b.name)
    // Pinned first, then favorited
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    if (a.favorited !== b.favorited) return a.favorited ? -1 : 1
    // Then by most recently used/created (descending)
    const aTime = a.last_used_at || a.created_at || ''
    const bTime = b.last_used_at || b.created_at || ''
    if (aTime !== bTime) return bTime.localeCompare(aTime)
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

  // Edit modal state (prompts / formatters)
  const [editingItem, setEditingItem] = useState<import('../../types/library').LibraryItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editItemId, setEditItemId] = useState<string | null>(null) // SearchSetItem ID
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  const openEditModal = async (item: import('../../types/library').LibraryItem) => {
    setEditingItem(item)
    setEditTitle(item.name)
    setEditContent(item.description || '')
    setEditError(null)
    setEditItemId(null)
    // Load the SearchSetItem content (the actual prompt text)
    if (item.item_uuid) {
      try {
        const items = await listSearchSetItems(item.item_uuid)
        if (items.length > 0) {
          setEditContent(items[0].searchphrase)
          setEditItemId(items[0].id)
        }
      } catch { /* ignore */ }
    }
  }

  const closeEditModal = () => {
    setEditingItem(null)
    setEditTitle('')
    setEditContent('')
    setEditItemId(null)
    setEditError(null)
  }

  const handleEditSave = async () => {
    if (!editingItem?.item_uuid) return
    setEditSaving(true)
    setEditError(null)
    try {
      await updateSearchSet(editingItem.item_uuid, { title: editTitle.trim() })
      if (editItemId) {
        await updateSearchSetItem(editItemId, { searchphrase: editContent, title: editTitle.trim() })
      }
      closeEditModal()
      refreshItems()
    } catch (e) {
      setEditError(e instanceof Error ? e.message : String(e))
    } finally {
      setEditSaving(false)
    }
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
        const ss = await createSearchSet({ title: createName.trim(), set_type: createModalType ?? 'extraction', extraction_config: config })
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
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  border: 'none',
                  padding: '6px 14px',
                  fontSize: 13,
                  fontWeight: 700,
                  color: 'var(--highlight-text-color, #000)',
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
                  setFolderMenuOpen(null)
                  setRenamingFolder(null)
                  setNewFolderMode(false)
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
            width: 148,
            flexShrink: 0,
            minHeight: 0,
            borderRight: '1px solid #f0f0f0',
            backgroundColor: '#fafafa',
            padding: '14px 0',
            overflowY: 'auto',
          }}
        >
          {/* Saved Views */}
          <div
            style={{
              padding: '0 12px',
              marginBottom: 6,
              fontSize: 10,
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
                  padding: '7px 10px 7px 12px',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                  backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                  borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                  transition: 'background 0.1s',
                }}
              >
                <Icon style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{label}</span>
                {count > 0 && (
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: '#aaa', fontWeight: 400 }}>{count}</span>
                )}
              </div>
            )
          })}

          {/* Collections section — only for Explore scope */}
          {scope === 'explore' && collections.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div
                style={{
                  padding: '0 12px',
                  marginBottom: 4,
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: '#888',
                  letterSpacing: '0.5px',
                }}
              >
                Collections
              </div>
              {collections.map((col) => {
                const isActive = viewFilter === `collection:${col.id}`
                return (
                  <div
                    key={col.id}
                    onClick={() => setViewFilter(isActive ? 'all' : `collection:${col.id}`)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '7px 10px 7px 12px',
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: isActive ? 600 : 500,
                      color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                      backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                      borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = '#f0f0f0' }}
                    onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = 'transparent' }}
                  >
                    <Layers style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {col.title}
                    </span>
                    <span style={{ marginLeft: 'auto', fontSize: 11, color: '#aaa', fontWeight: 400 }}>
                      {col.item_ids.length}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Folders section — only for personal and team scopes */}
          {scope !== 'explore' && (
            <div style={{ marginTop: 16 }}>
              {/* Folders header row */}
              <div
                style={{
                  padding: '0 8px 0 12px',
                  marginBottom: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: '#888', letterSpacing: '0.5px' }}>
                  Folders
                </span>
                <button
                  title="New folder"
                  onClick={() => { setNewFolderMode(true); setNewFolderName('') }}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '2px 4px',
                    cursor: 'pointer',
                    color: '#aaa',
                    display: 'flex',
                    alignItems: 'center',
                    borderRadius: 4,
                    lineHeight: 1,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#555' }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = '#aaa' }}
                >
                  <FolderPlus style={{ width: 13, height: 13 }} />
                </button>
              </div>

              {/* New folder input */}
              {newFolderMode && (
                <div style={{ padding: '4px 8px 4px 12px' }}>
                  <input
                    autoFocus
                    type="text"
                    value={newFolderName}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    placeholder="Folder name"
                    onKeyDown={async (e) => {
                      if (e.key === 'Enter' && newFolderName.trim()) {
                        await createFolder(newFolderName.trim())
                        setNewFolderMode(false)
                        setNewFolderName('')
                      } else if (e.key === 'Escape') {
                        setNewFolderMode(false)
                        setNewFolderName('')
                      }
                    }}
                    onBlur={() => {
                      setNewFolderMode(false)
                      setNewFolderName('')
                    }}
                    style={{
                      width: '100%',
                      fontSize: 12,
                      padding: '4px 6px',
                      border: '1px solid #dadce0',
                      borderRadius: 5,
                      outline: 'none',
                      fontFamily: 'inherit',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              )}

              {/* Folder list */}
              {folders.length === 0 && !newFolderMode && (
                <div style={{ padding: '4px 12px', fontSize: 11, color: '#bbb', fontStyle: 'italic' }}>
                  No folders yet
                </div>
              )}
              {folders.map((folder) => {
                const isActive = viewFilter === folder.uuid
                const isRenaming = renamingFolder === folder.uuid
                const isMenuOpen = folderMenuOpen === folder.uuid
                return (
                  <div
                    key={folder.uuid}
                    style={{ position: 'relative' }}
                  >
                    {isRenaming ? (
                      <div style={{ padding: '4px 8px 4px 12px' }}>
                        <input
                          autoFocus
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={async (e) => {
                            if (e.key === 'Enter' && renameValue.trim()) {
                              await renameFolder(folder.uuid, renameValue.trim())
                              setRenamingFolder(null)
                            } else if (e.key === 'Escape') {
                              setRenamingFolder(null)
                            }
                          }}
                          onBlur={async () => {
                            if (renameValue.trim()) {
                              await renameFolder(folder.uuid, renameValue.trim())
                            }
                            setRenamingFolder(null)
                          }}
                          style={{
                            width: '100%',
                            fontSize: 12,
                            padding: '4px 6px',
                            border: '1px solid #dadce0',
                            borderRadius: 5,
                            outline: 'none',
                            fontFamily: 'inherit',
                            boxSizing: 'border-box',
                          }}
                        />
                      </div>
                    ) : (
                      <div
                        onClick={() => setViewFilter(isActive ? 'all' : folder.uuid)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '7px 6px 7px 12px',
                          cursor: 'pointer',
                          fontSize: 12,
                          fontWeight: isActive ? 600 : 500,
                          color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                          backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                          borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                          transition: 'background 0.1s',
                          gap: 0,
                        }}
                        onMouseEnter={(e) => {
                          if (!isActive) e.currentTarget.style.backgroundColor = '#f0f0f0'
                          const btn = e.currentTarget.querySelector('.folder-menu-btn') as HTMLElement
                          if (btn) btn.style.opacity = '1'
                        }}
                        onMouseLeave={(e) => {
                          if (!isActive) e.currentTarget.style.backgroundColor = 'transparent'
                          if (!isMenuOpen) {
                            const btn = e.currentTarget.querySelector('.folder-menu-btn') as HTMLElement
                            if (btn) btn.style.opacity = '0'
                          }
                        }}
                      >
                        {isActive
                          ? <FolderOpen style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                          : <Folder style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                        }
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {folder.name}
                        </span>
                        <span style={{ fontSize: 11, color: '#999', marginRight: 4, flexShrink: 0 }}>
                          {folder.item_count}
                        </span>
                        <button
                          className="folder-menu-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (!isMenuOpen) {
                              const rect = e.currentTarget.getBoundingClientRect()
                              setFolderMenuPos({ top: rect.bottom + 4, left: rect.left })
                            }
                            setFolderMenuOpen(isMenuOpen ? null : folder.uuid)
                          }}
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: '2px 3px',
                            cursor: 'pointer',
                            color: '#888',
                            display: 'flex',
                            alignItems: 'center',
                            borderRadius: 4,
                            opacity: isMenuOpen ? 1 : 0,
                            transition: 'opacity 0.1s',
                            flexShrink: 0,
                          }}
                        >
                          <MoreHorizontal style={{ width: 12, height: 12 }} />
                        </button>
                      </div>
                    )}

                    {/* Folder context menu — rendered via portal to escape overflow:hidden */}
                    {isMenuOpen && createPortal(
                      <div
                        ref={folderMenuRef}
                        style={{
                          position: 'fixed',
                          left: folderMenuPos.left,
                          top: folderMenuPos.top,
                          zIndex: 9999,
                          minWidth: 140,
                          borderRadius: 8,
                          border: '1px solid rgba(0,0,0,0.14)',
                          background: '#fff',
                          boxShadow: '0 6px 18px rgba(0,0,0,0.14)',
                          padding: 4,
                        }}
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setRenamingFolder(folder.uuid)
                            setRenameValue(folder.name)
                            setFolderMenuOpen(null)
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            width: '100%',
                            background: 'none',
                            border: 'none',
                            padding: '8px 10px',
                            fontSize: 12,
                            color: '#1f2937',
                            cursor: 'pointer',
                            borderRadius: 5,
                            textAlign: 'left',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                        >
                          <Pencil style={{ width: 12, height: 12, color: '#6b7280' }} />
                          Rename
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation()
                            await removeFolder(folder.uuid)
                            if (viewFilter === folder.uuid) setViewFilter('all')
                            setFolderMenuOpen(null)
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            width: '100%',
                            background: 'none',
                            border: 'none',
                            padding: '8px 10px',
                            fontSize: 12,
                            color: '#dc2626',
                            cursor: 'pointer',
                            borderRadius: 5,
                            textAlign: 'left',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#fef2f2' }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                        >
                          <Trash2 style={{ width: 12, height: 12 }} />
                          Delete
                        </button>
                      </div>,
                      document.body,
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Results pane */}
        <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', backgroundColor: '#fff', borderRight: '1px solid #f0f0f0' }}>
          {/* Collection filter banner */}
          {selectedCollection && (
            <div style={{ padding: '12px 24px', background: '#f8f9fa', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{selectedCollection.title}</div>
                {selectedCollection.description && (
                  <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>{selectedCollection.description}</div>
                )}
              </div>
              <button
                onClick={() => setViewFilter('all')}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 4,
                  cursor: 'pointer',
                  color: '#888',
                  display: 'flex',
                  alignItems: 'center',
                  borderRadius: 4,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#333' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#888' }}
              >
                <X style={{ width: 16, height: 16 }} />
              </button>
            </div>
          )}

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
                  onEdit={openEditModal}
                  onMoveToFolder={scope !== 'explore' ? handleMoveToFolder : undefined}
                  folders={scope !== 'explore' ? folders : undefined}
                  qualityTier={item.quality_tier}
                  qualityScore={item.quality_score}
                  onOpen={(it) => {
                    touchItem(it.id).then(() => refreshItems()).catch(() => {})
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

      {/* Edit Modal (prompts / formatters) */}
      {editingItem && (
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
          onClick={closeEditModal}
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
            <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 600, color: '#202124' }}>
              Edit {editingItem.set_type === 'formatter' ? 'Formatter' : 'Prompt'}
            </h2>
            <div style={{ marginBottom: 16 }}>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder="Title"
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
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                placeholder={editingItem.set_type === 'formatter' ? 'Write your formatting instructions here' : 'Write your prompt here'}
                rows={10}
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
            {editError && (
              <div style={{ marginBottom: 12, padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: '#dc2626' }}>
                {editError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleEditSave}
                disabled={editSaving || !editTitle.trim()}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  cursor: editSaving || !editTitle.trim() ? 'not-allowed' : 'pointer',
                  opacity: editSaving || !editTitle.trim() ? 0.5 : 1,
                }}
              >
                {editSaving ? 'Saving...' : 'Update'}
              </button>
              <button
                onClick={closeEditModal}
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
                Cancel
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
