import { useCallback, useMemo, useState, useRef, useEffect } from 'react'
import { Plus, Folder as FolderIcon, Upload, Trash2, Download } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { useTeams } from '../../hooks/useTeams'
import { useDocuments } from '../../hooks/useDocuments'
import { useBreadcrumbs } from '../../hooks/useFolders'
import { useUpload } from '../../hooks/useUpload'
import { Breadcrumbs } from './Breadcrumbs'
import { FileList } from './FileList'
import { UploadZone } from './UploadZone'
import { UploadProgress } from './UploadProgress'
import { ContextMenu } from './ContextMenu'
import { RenameDialog } from './RenameDialog'
import { CreateFolderDialog } from './CreateFolderDialog'
import { deleteFile, renameFile, downloadFileUrl } from '../../api/files'
import { createFolder, renameFolder, deleteFolder } from '../../api/folders'
import type { Document, Folder } from '../../types/document'

export interface ContentMatch {
  uuid: string
  title: string
  snippet: string
}

interface FileBrowserProps {
  onDocClick?: (doc: Document) => void
  searchQuery?: string
  contentMatches?: ContentMatch[]
}

export function FileBrowser({ onDocClick, searchQuery = '', contentMatches }: FileBrowserProps) {
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const space = user?.user_id || ''

  const [currentFolder, setCurrentFolder] = useState<string | null>(null)
  const { documents, folders, loading, refresh } = useDocuments(space, currentFolder, currentTeam?.uuid)
  const { breadcrumbs } = useBreadcrumbs(currentFolder)
  const { uploads, upload, lastUploadedUuid, clearLastUploaded } = useUpload(space, currentFolder, refresh)

  // Auto-open the first document after upload
  useEffect(() => {
    if (!lastUploadedUuid || documents.length === 0) return
    const doc = documents.find(d => d.uuid === lastUploadedUuid)
    if (doc) {
      onDocClick?.(doc)
      clearLastUploaded()
    }
  }, [lastUploadedUuid, documents, onDocClick, clearLastUploaded])

  // Bulk selection
  const [selectedUuids, setSelectedUuids] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // Clear selection when navigating folders
  useEffect(() => {
    setSelectedUuids(new Set())
  }, [currentFolder])

  // Search (query provided via prop, content matches from API)
  const filteredFolders = useMemo(() => {
    if (!searchQuery.trim()) return folders
    const q = searchQuery.toLowerCase()
    return folders.filter(f => f.title.toLowerCase().includes(q))
  }, [folders, searchQuery])

  // Build a set of content-matched UUIDs and a snippet map
  const contentMatchUuids = useMemo(() => {
    if (!contentMatches) return new Set<string>()
    return new Set(contentMatches.map(m => m.uuid))
  }, [contentMatches])

  const snippetMap = useMemo(() => {
    const map = new Map<string, string>()
    if (contentMatches) {
      for (const m of contentMatches) {
        if (m.snippet) map.set(m.uuid, m.snippet)
      }
    }
    return map
  }, [contentMatches])

  const filteredDocuments = useMemo(() => {
    if (!searchQuery.trim()) return documents
    const q = searchQuery.toLowerCase()
    // Include docs matching by title OR by content
    return documents.filter(d =>
      d.title.toLowerCase().includes(q) || contentMatchUuids.has(d.uuid)
    )
  }, [documents, searchQuery, contentMatchUuids])

  const handleToggleSelect = useCallback((uuid: string) => {
    setSelectedUuids(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }, [])

  const handleToggleAll = useCallback(() => {
    const allUuids = [...filteredFolders.map(f => f.uuid), ...filteredDocuments.map(d => d.uuid)]
    setSelectedUuids(prev => {
      const allSelected = allUuids.every(u => prev.has(u))
      return allSelected ? new Set() : new Set(allUuids)
    })
  }, [filteredFolders, filteredDocuments])

  const handleBulkDelete = useCallback(async () => {
    if (selectedUuids.size === 0) return
    setBulkDeleting(true)
    try {
      const promises: Promise<unknown>[] = []
      for (const uuid of selectedUuids) {
        const isFolder = folders.some(f => f.uuid === uuid)
        if (isFolder) promises.push(deleteFolder(uuid))
        else promises.push(deleteFile(uuid))
      }
      await Promise.all(promises)
      setSelectedUuids(new Set())
      refresh()
    } finally {
      setBulkDeleting(false)
    }
  }, [selectedUuids, folders, refresh])

  const handleBulkDownload = useCallback(() => {
    const docUuids = [...selectedUuids].filter(u => documents.some(d => d.uuid === u))
    for (const uuid of docUuids) {
      window.open(downloadFileUrl(uuid), '_blank')
    }
  }, [selectedUuids, documents])

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    type: 'folder' | 'doc'
    item: Folder | Document
  } | null>(null)

  // + Add dropdown
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const addMenuRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (addMenuRef.current && !addMenuRef.current.contains(e.target as Node)) {
        setAddMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Dialog state
  const [renameTarget, setRenameTarget] = useState<{
    type: 'folder' | 'doc'
    uuid: string
    name: string
  } | null>(null)
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [createTeamFolder, setCreateTeamFolder] = useState(false)

  const handleFolderContextMenu = useCallback((folder: Folder, e: React.MouseEvent) => {
    setContextMenu({ x: e.clientX, y: e.clientY, type: 'folder', item: folder })
  }, [])

  const handleDocContextMenu = useCallback((doc: Document, e: React.MouseEvent) => {
    setContextMenu({ x: e.clientX, y: e.clientY, type: 'doc', item: doc })
  }, [])

  const handleRename = useCallback(
    async (newName: string) => {
      if (!renameTarget) return
      if (renameTarget.type === 'doc') {
        await renameFile(renameTarget.uuid, newName)
      } else {
        await renameFolder(renameTarget.uuid, newName)
      }
      setRenameTarget(null)
      refresh()
    },
    [renameTarget, refresh],
  )

  const handleCreateFolder = useCallback(
    async (name: string) => {
      await createFolder({
        name,
        parent_id: currentFolder || '0',
        space,
        ...(createTeamFolder ? { folder_type: 'team' } : {}),
      })
      setShowCreateFolder(false)
      setCreateTeamFolder(false)
      refresh()
    },
    [currentFolder, space, createTeamFolder, refresh],
  )

  const handleDelete = useCallback(
    async (type: 'folder' | 'doc', uuid: string) => {
      if (type === 'doc') {
        await deleteFile(uuid)
      } else {
        await deleteFolder(uuid)
      }
      refresh()
    },
    [refresh],
  )

  if (loading && documents.length === 0 && folders.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  return (
    <div style={{ padding: '0px 45px 45px 45px' }}>
      <UploadZone onFilesSelected={(files) => upload(files)} />
      <UploadProgress uploads={uploads} />

      {/* + Add button with dropdown menu - matches Flask _add_button.html */}
      <div ref={addMenuRef} className="relative inline-block mt-4">
        <button
          onClick={() => setAddMenuOpen(!addMenuOpen)}
          className="flex items-center gap-1 rounded-[var(--ui-radius)] bg-highlight text-highlight-text px-3 py-1.5 text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <Plus className="h-4 w-4" />
          Add
        </button>

        {addMenuOpen && (
          <div
            className="absolute left-0 z-[1000] mt-2 min-w-[180px] rounded-lg border bg-white p-1.5"
            style={{
              borderColor: 'rgba(0,0,0,.15)',
              boxShadow: '0 8px 24px rgba(0,0,0,.12)',
            }}
          >
            <button
              onClick={() => {
                setShowCreateFolder(true)
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <FolderIcon className="h-4 w-4 shrink-0 text-[#a2a2a2]" style={{ width: 18 }} />
              <span>New Folder</span>
            </button>
            <button
              onClick={() => {
                setCreateTeamFolder(true)
                setShowCreateFolder(true)
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <FolderIcon className="h-4 w-4 shrink-0 text-[rgb(0,128,128)]" style={{ width: 18 }} />
              <span>New Team Folder</span>
            </button>
            <button
              onClick={() => {
                fileInputRef.current?.click()
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <Upload className="h-4 w-4 shrink-0" style={{ width: 18 }} />
              <span>Upload Files</span>
            </button>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.xlsx,.xls"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {/* Breadcrumbs - matches Flask _breadcrumbs.html */}
      <Breadcrumbs items={breadcrumbs} onNavigate={setCurrentFolder} />

      {/* Bulk action toolbar */}
      {selectedUuids.size > 0 && (
        <div
          className="mt-2.5 flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)', border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)' }}
        >
          <span className="text-sm font-medium" style={{ color: '#374151' }}>
            {selectedUuids.size} selected
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={handleBulkDownload}
              disabled={![...selectedUuids].some(u => documents.some(d => d.uuid === u))}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              Download
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {bulkDeleting ? 'Deleting...' : 'Delete'}
            </button>
            <button
              onClick={() => setSelectedUuids(new Set())}
              className="text-xs text-gray-500 hover:text-gray-700 px-1.5"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* File table - matches Flask .styled-table */}
      <div
        className="mt-2.5 rounded-[12px] overflow-hidden"
        style={{ boxShadow: '0 0 20px rgba(0, 0, 0, 0.15)' }}
      >
        <FileList
          folders={filteredFolders}
          documents={filteredDocuments}
          onFolderClick={setCurrentFolder}
          onFolderContextMenu={handleFolderContextMenu}
          onDocContextMenu={handleDocContextMenu}
          onDocClick={onDocClick}
          selectedUuids={selectedUuids}
          onToggleSelect={handleToggleSelect}
          onToggleAll={handleToggleAll}
          snippets={searchQuery.trim() ? snippetMap : undefined}
        />
      </div>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onRename={() => {
            const item = contextMenu.item
            setRenameTarget({
              type: contextMenu.type,
              uuid: item.uuid,
              name: item.title,
            })
          }}
          onDelete={() => handleDelete(contextMenu.type, contextMenu.item.uuid)}
          onDownload={
            contextMenu.type === 'doc'
              ? () => {
                  window.open(downloadFileUrl(contextMenu.item.uuid), '_blank')
                }
              : undefined
          }
          onCopyUuid={() => {
            navigator.clipboard.writeText(contextMenu.item.uuid)
          }}
        />
      )}

      {renameTarget && (
        <RenameDialog
          currentName={renameTarget.name}
          onSubmit={handleRename}
          onClose={() => setRenameTarget(null)}
        />
      )}

      {showCreateFolder && (
        <CreateFolderDialog
          onSubmit={handleCreateFolder}
          onClose={() => { setShowCreateFolder(false); setCreateTeamFolder(false) }}
          title={createTeamFolder ? 'New Team Folder' : 'New Folder'}
        />
      )}
    </div>
  )
}
