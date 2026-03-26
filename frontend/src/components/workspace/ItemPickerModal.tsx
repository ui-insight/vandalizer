import { useEffect, useRef, useState } from 'react'
import { Search, X, Workflow, FileText, Users, Compass, Loader2 } from 'lucide-react'
import { listWorkflows } from '../../api/workflows'
import { listSearchSets } from '../../api/extractions'
import { listVerifiedItems } from '../../api/library'

type ScopeTab = 'mine' | 'team' | 'explore'

interface PickerItem {
  id: string
  name: string
  description?: string | null
  owner?: 'mine' | 'team' | 'explore'
  qualityTier?: string | null
}

interface Props {
  kind: 'workflow' | 'extraction'
  onSelect: (id: string, name: string) => void
  onClose: () => void
  currentId?: string
}

export function ItemPickerModal({ kind, onSelect, onClose, currentId }: Props) {
  const [scope, setScope] = useState<ScopeTab>('mine')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [items, setItems] = useState<PickerItem[]>([])
  const [loading, setLoading] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const backdropRef = useRef<HTMLDivElement>(null)

  // Debounce search input
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [search])

  // Focus search on open
  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Fetch items when scope or search changes
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    const fetchItems = async () => {
      try {
        let result: PickerItem[] = []

        if (scope === 'explore') {
          // Use the verified catalog API
          const filterKind = kind === 'workflow' ? 'workflow' : 'search_set'
          const data = await listVerifiedItems({
            kind: filterKind,
            search: debouncedSearch || undefined,
            limit: 50,
          })
          result = data.items.map(item => ({
            // source_uuid has the correct ID for navigation: uuid for search sets, _id for workflows
            id: item.source_uuid || item.item_id,
            name: item.display_name || item.name,
            description: item.description,
            owner: 'explore' as const,
            qualityTier: item.quality_tier,
          }))
        } else if (kind === 'workflow') {
          const workflows = await listWorkflows({
            scope,
            search: debouncedSearch || undefined,
          })
          result = workflows.map(wf => ({
            id: wf.id,
            name: wf.name,
            description: wf.description,
            owner: scope as 'mine' | 'team',
          }))
        } else {
          const sets = await listSearchSets({
            scope,
            search: debouncedSearch || undefined,
          })
          result = sets.map(ss => ({
            id: kind === 'extraction' ? ss.uuid : ss.id,
            name: ss.title,
            description: null,
            owner: scope as 'mine' | 'team',
            qualityTier: ss.quality_tier,
          }))
        }

        if (!cancelled) {
          setItems(result)
          setLoading(false)
        }
      } catch {
        if (!cancelled) {
          setItems([])
          setLoading(false)
        }
      }
    }

    fetchItems()
    return () => { cancelled = true }
  }, [scope, debouncedSearch, kind])

  const kindLabel = kind === 'workflow' ? 'Workflow' : 'Extraction'

  const SCOPE_TABS: { value: ScopeTab; label: string; icon: typeof Workflow }[] = [
    { value: 'mine', label: 'Mine', icon: FileText },
    { value: 'team', label: 'Team', icon: Users },
    { value: 'explore', label: 'Explore', icon: Compass },
  ]

  const tierColors: Record<string, { bg: string; text: string }> = {
    gold: { bg: '#fef3c7', text: '#92400e' },
    silver: { bg: '#f3f4f6', text: '#4b5563' },
    bronze: { bg: '#fed7aa', text: '#9a3412' },
  }

  return (
    <div
      ref={backdropRef}
      onClick={e => { if (e.target === backdropRef.current) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div style={{
        backgroundColor: '#fff', borderRadius: 12,
        width: '100%', maxWidth: 560, maxHeight: '80vh',
        display: 'flex', flexDirection: 'column',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px 0', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#111827' }}>
            Select {kindLabel}
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#6b7280', padding: 4, borderRadius: 6,
              display: 'flex', alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Search bar */}
        <div style={{ padding: '12px 20px 0' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 12px', backgroundColor: '#f9fafb',
            border: '1.5px solid #e5e7eb', borderRadius: 8,
          }}>
            <Search size={16} style={{ color: '#9ca3af', flexShrink: 0 }} />
            <input
              ref={searchRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={`Search ${kind === 'workflow' ? 'workflows' : 'extractions'}...`}
              style={{
                border: 'none', outline: 'none', flex: 1,
                backgroundColor: 'transparent', fontSize: 14,
                fontFamily: 'inherit', color: '#111827',
              }}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#9ca3af', padding: 2, display: 'flex',
                }}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Scope tabs */}
        <div style={{
          display: 'flex', gap: 0, padding: '12px 20px 0',
          borderBottom: '1px solid #e5e7eb',
        }}>
          {SCOPE_TABS.map(tab => {
            const active = scope === tab.value
            const Icon = tab.icon
            return (
              <button
                key={tab.value}
                onClick={() => setScope(tab.value)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '8px 16px', fontSize: 13, fontWeight: 600,
                  fontFamily: 'inherit', cursor: 'pointer',
                  color: active ? '#2563eb' : '#6b7280',
                  backgroundColor: 'transparent', border: 'none',
                  borderBottom: active ? '2px solid #2563eb' : '2px solid transparent',
                  marginBottom: -1, transition: 'color 0.15s',
                }}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            )
          })}
        </div>

        {/* Items list */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '8px 12px 12px',
          minHeight: 200,
        }}>
          {loading ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, padding: 40, color: '#9ca3af', fontSize: 13,
            }}>
              <Loader2 size={16} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
              Loading...
            </div>
          ) : items.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: '40px 20px', color: '#9ca3af', fontSize: 13,
            }}>
              {debouncedSearch
                ? `No ${kind === 'workflow' ? 'workflows' : 'extractions'} matching "${debouncedSearch}"`
                : scope === 'mine'
                  ? `You haven't created any ${kind === 'workflow' ? 'workflows' : 'extractions'} yet.`
                  : scope === 'team'
                    ? `No team ${kind === 'workflow' ? 'workflows' : 'extractions'} found.`
                    : `No verified ${kind === 'workflow' ? 'workflows' : 'extractions'} available.`
              }
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {items.map(item => {
                const isSelected = item.id === currentId
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item.id, item.name)}
                    style={{
                      display: 'flex', alignItems: 'flex-start', gap: 12,
                      padding: '10px 12px', textAlign: 'left', width: '100%',
                      backgroundColor: isSelected ? '#eff6ff' : '#fff',
                      border: isSelected ? '1.5px solid #3b82f6' : '1.5px solid transparent',
                      borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                      transition: 'background-color 0.1s, border-color 0.1s',
                    }}
                    onMouseEnter={e => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = '#f9fafb'
                    }}
                    onMouseLeave={e => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = '#fff'
                    }}
                  >
                    <div style={{
                      width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                      backgroundColor: kind === 'workflow' ? '#ede9fe' : '#dbeafe',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginTop: 1,
                    }}>
                      {kind === 'workflow'
                        ? <Workflow size={16} style={{ color: '#7c3aed' }} />
                        : <FileText size={16} style={{ color: '#2563eb' }} />
                      }
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 14, fontWeight: 600, color: '#111827',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {item.name}
                      </div>
                      {item.description && (
                        <div style={{
                          fontSize: 12, color: '#6b7280', marginTop: 2,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {item.description}
                        </div>
                      )}
                    </div>
                    {item.qualityTier && tierColors[item.qualityTier] && (
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 8px',
                        borderRadius: 10, textTransform: 'uppercase', flexShrink: 0,
                        backgroundColor: tierColors[item.qualityTier].bg,
                        color: tierColors[item.qualityTier].text,
                      }}>
                        {item.qualityTier}
                      </span>
                    )}
                    {isSelected && (
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 8px',
                        borderRadius: 10, backgroundColor: '#dbeafe', color: '#1d4ed8',
                        flexShrink: 0,
                      }}>
                        Selected
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
