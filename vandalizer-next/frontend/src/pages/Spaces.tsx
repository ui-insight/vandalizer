import { useEffect, useState } from 'react'
import { FolderOpen, Plus, Trash2, Pencil, Check, X } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { listSpaces, createSpace, updateSpace, deleteSpace } from '../api/spaces'
import type { Space } from '../api/spaces'

export default function Spaces() {
  const [spaces, setSpaces] = useState<Space[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  useEffect(() => {
    listSpaces()
      .then(setSpaces)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      const space = await createSpace(newTitle.trim())
      setSpaces(prev => [...prev, space])
      setNewTitle('')
      setShowCreate(false)
    } catch { /* ignore */ }
    finally { setCreating(false) }
  }

  const handleRename = async (uuid: string) => {
    if (!editTitle.trim()) return
    try {
      const updated = await updateSpace(uuid, { title: editTitle.trim() })
      setSpaces(prev => prev.map(s => s.uuid === uuid ? updated : s))
      setEditingId(null)
    } catch { /* ignore */ }
  }

  const handleDelete = async (uuid: string) => {
    if (!confirm('Delete this space? Documents in this space will not be deleted.')) return
    try {
      await deleteSpace(uuid)
      setSpaces(prev => prev.filter(s => s.uuid !== uuid))
    } catch { /* ignore */ }
  }

  return (
    <PageLayout>
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <FolderOpen size={22} color="#6b7280" />
            <h1 style={{ fontSize: 22, fontWeight: 700 }}>Spaces</h1>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
              borderRadius: 'var(--ui-radius, 12px)', border: 'none',
              background: 'var(--highlight-color, #eab308)', color: '#000',
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Plus size={16} /> New Space
          </button>
        </div>

        <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 20 }}>
          Spaces help you organize documents, workflows, and conversations into separate projects or categories.
        </p>

        {/* Create form */}
        {showCreate && (
          <div style={{
            padding: 16, background: '#fff', border: '1px solid #e5e7eb',
            borderRadius: 'var(--ui-radius, 12px)', marginBottom: 16,
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <input
              autoFocus
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setShowCreate(false) }}
              placeholder="Space name..."
              style={{
                flex: 1, padding: '8px 12px', borderRadius: 'var(--ui-radius, 12px)',
                border: '1px solid #d1d5db', fontSize: 14, outline: 'none',
              }}
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newTitle.trim()}
              style={{
                padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: 'var(--highlight-color, #eab308)', color: '#000',
                fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: creating ? 0.6 : 1,
              }}
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
            >
              <X size={18} />
            </button>
          </div>
        )}

        {/* Space list */}
        <div style={{
          background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
          overflow: 'hidden',
        }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>Loading spaces...</div>
          ) : spaces.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center' }}>
              <FolderOpen size={32} color="#d1d5db" style={{ margin: '0 auto 12px' }} />
              <div style={{ fontSize: 14, color: '#6b7280' }}>No spaces created yet.</div>
              <div style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>Create a space to start organizing your work.</div>
            </div>
          ) : (
            spaces.map((space, i) => (
              <div
                key={space.uuid}
                style={{
                  display: 'flex', alignItems: 'center', padding: '14px 20px',
                  borderBottom: i < spaces.length - 1 ? '1px solid #f3f4f6' : 'none',
                  gap: 12,
                }}
              >
                <FolderOpen size={18} color="#9ca3af" />

                {editingId === space.uuid ? (
                  <>
                    <input
                      autoFocus
                      value={editTitle}
                      onChange={e => setEditTitle(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRename(space.uuid); if (e.key === 'Escape') setEditingId(null) }}
                      style={{
                        flex: 1, padding: '4px 8px', borderRadius: 6,
                        border: '1px solid #d1d5db', fontSize: 14, outline: 'none',
                      }}
                    />
                    <button
                      onClick={() => handleRename(space.uuid)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#16a34a', padding: 4 }}
                    >
                      <Check size={16} />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
                    >
                      <X size={16} />
                    </button>
                  </>
                ) : (
                  <>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 500 }}>{space.title}</div>
                      <div style={{ fontSize: 12, color: '#9ca3af', fontFamily: 'ui-monospace, monospace' }}>
                        {space.uuid.slice(0, 12)}...
                      </div>
                    </div>
                    <button
                      onClick={() => { setEditingId(space.uuid); setEditTitle(space.title) }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 4 }}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => handleDelete(space.uuid)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </PageLayout>
  )
}
