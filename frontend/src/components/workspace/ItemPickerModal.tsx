import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Search, X, Workflow, FileText, Users, Compass, Loader2, Pin, Star } from 'lucide-react'
import { listLibraries, listItems, listVerifiedItems } from '../../api/library'
import { useAuth } from '../../hooks/useAuth'
import type { Library } from '../../types/library'

type ScopeTab = 'mine' | 'team' | 'explore'

interface PickerItem {
  id: string
  name: string
  description?: string | null
  owner?: 'mine' | 'team' | 'explore'
  qualityTier?: string | null
  pinned?: boolean
  favorited?: boolean
}

// Pinned first, then favorited, then the rest; stable within each group.
const pickerRank = (item: PickerItem) => (item.pinned ? 0 : item.favorited ? 1 : 2)

// 'extraction', 'prompt', and 'formatter' are all backed by SearchSet records
// (distinguished by set_type); 'workflow' is a Workflow. The picker maps these
// semantic kinds to the backend library kind and filters by set_type.
type PickerKind = 'workflow' | 'extraction' | 'prompt' | 'formatter'

interface Props {
  kind: PickerKind
  onSelect: (id: string, name: string) => void
  onClose: () => void
  currentId?: string
  /** When true, fills the parent container instead of using a fixed viewport overlay */
  inline?: boolean
}

export function ItemPickerModal({ kind, onSelect, onClose, currentId, inline }: Props) {
  const { user } = useAuth()
  const teamId = user?.current_team ?? undefined
  const [scope, setScope] = useState<ScopeTab>('mine')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [items, setItems] = useState<PickerItem[]>([])
  const [loading, setLoading] = useState(false)
  const [libraries, setLibraries] = useState<Library[] | null>(null)
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [libraryRetry, setLibraryRetry] = useState(0)
  const searchRef = useRef<HTMLInputElement>(null)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const backdropRef = useRef<HTMLDivElement>(null)

  // Fetch libraries on mount to get personal/team library IDs
  useEffect(() => {
    let cancelled = false
    setLibraries(null)
    setLibraryError(null)
    listLibraries(teamId)
      .then(result => { if (!cancelled) setLibraries(result) })
      .catch(() => { if (!cancelled) setLibraryError('Could not load your libraries. Please retry.') })
    return () => { cancelled = true }
  }, [teamId, libraryRetry])

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
  usePanelEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Consume Escape before closing: a parent wizard may re-render and
        // install its window handler during this same event's propagation.
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Fetch items when scope or search changes
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    if (scope !== 'explore' && !libraries) return

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
        } else {
          // Use library items so mine/team tabs match the Library page
          const targetScope = scope === 'mine' ? 'personal' : 'team'
          const lib = libraries?.find(l => l.scope === targetScope)
          if (lib) {
            const filterKind = kind === 'workflow' ? 'workflow' : 'search_set'
            let libItems = await listItems(lib.id, {
              kind: filterKind,
              search: debouncedSearch || undefined,
            })
            // All three SearchSet-backed kinds share the 'search_set' library
            // kind, so narrow by set_type. Legacy sets with no set_type are
            // treated as extractions.
            if (kind !== 'workflow') {
              libItems = libItems.filter(item =>
                kind === 'extraction'
                  ? (item.set_type === 'extraction' || item.set_type == null)
                  : item.set_type === kind,
              )
            }
            result = libItems.map(item => ({
              // item_id is the Workflow _id; item_uuid is the SearchSet uuid
              id: kind === 'workflow' ? item.item_id : (item.item_uuid || item.item_id),
              name: item.name,
              description: item.description,
              owner: scope as 'mine' | 'team',
              qualityTier: item.quality_tier,
              pinned: item.pinned,
              favorited: item.favorited,
            }))
            result.sort((a, b) => pickerRank(a) - pickerRank(b))
          }
        }

        if (!cancelled) {
          setItems(result)
          setLoading(false)
        }
      } catch {
        if (!cancelled) {
          setItems([])
          setError('Could not load items. Please retry.')
          setLoading(false)
        }
      }
    }

    fetchItems()
    return () => { cancelled = true }
  }, [scope, debouncedSearch, kind, libraries, retry])

  const kindLabel = kind === 'workflow' ? 'Workflow'
    : kind === 'prompt' ? 'Prompt'
    : kind === 'formatter' ? 'Formatter'
    : 'Extraction'
  const kindPlural = kind === 'workflow' ? 'workflows'
    : kind === 'prompt' ? 'prompts'
    : kind === 'formatter' ? 'formatters'
    : 'extractions'

  // The verified catalog has no set_type, so it can't distinguish prompts /
  // formatters from extractions — only offer Explore for the kinds it serves.
  const SCOPE_TABS: { value: ScopeTab; label: string; icon: typeof Workflow }[] = [
    { value: 'mine', label: 'Mine', icon: FileText },
    { value: 'team', label: 'Team', icon: Users },
    ...(kind === 'prompt' || kind === 'formatter'
      ? []
      : [{ value: 'explore' as const, label: 'Explore', icon: Compass }]),
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
      style={inline ? {
        position: 'absolute', inset: 0, zIndex: 50,
        backgroundColor: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 'var(--workspace-space-16)',
      } : {
        position: 'fixed', inset: 0, zIndex: 9999,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 'var(--workspace-space-20)',
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="action-picker"
        role="dialog"
        aria-modal="true"
        aria-label={`Select ${kindLabel}`}
        style={{
        backgroundColor: '#fff', borderRadius: 'var(--workspace-radius-large)',
        width: '100%', maxWidth: inline ? 480 : 560, maxHeight: inline ? '90%' : '80vh',
        display: 'flex', flexDirection: 'column',
        boxShadow: 'var(--workspace-shadow-dialog)',
      }}>
        {/* Header */}
        <div style={{
          padding: "var(--workspace-space-16) var(--workspace-space-20) 0", display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 700, color: '#111827' }}>
            Select {kindLabel}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#555e68', padding: 'var(--workspace-space-4)', borderRadius: 'var(--workspace-radius-small)',
              display: 'flex', alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Search bar */}
        <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-20) 0" }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)',
            padding: "var(--workspace-space-8) var(--workspace-space-12)", backgroundColor: '#f9fafb',
            border: "1.5px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-medium)',
          }}>
            <Search size={16} style={{ color: '#9ca3af', flexShrink: 0 }} />
            <input
              ref={searchRef}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={`Search ${kindPlural}...`}
              aria-label={`Search ${kindPlural}`}
              style={{
                border: 'none', flex: 1, minWidth: 0,
                backgroundColor: 'transparent', fontSize: 'var(--workspace-font-body)',
                fontFamily: 'inherit', color: '#111827',
              }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="Clear search"
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#9ca3af', padding: 'var(--workspace-space-2)', display: 'flex',
                }}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Scope tabs */}
        <div style={{
          display: 'flex', gap: 0, padding: "var(--workspace-space-12) var(--workspace-space-20) 0",
          borderBottom: "1px solid var(--workspace-border)",
        }}>
          {SCOPE_TABS.map(tab => {
            const active = scope === tab.value
            const Icon = tab.icon
            return (
              <button
                key={tab.value}
                type="button"
                aria-pressed={active}
                onClick={() => setScope(tab.value)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
                  padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-control)', fontWeight: 600,
                  fontFamily: 'inherit', cursor: 'pointer',
                  color: active ? 'var(--highlight-on-light, #806600)' : '#555e68',
                  backgroundColor: 'transparent', border: 'none',
                  borderBottom: active ? '2px solid var(--highlight-on-light, #806600)' : '2px solid transparent',
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
          flex: 1, overflowY: 'auto', padding: "var(--workspace-space-8) var(--workspace-space-12) var(--workspace-space-12)",
          minHeight: 0,
        }}>
          {(error || (scope !== 'explore' && libraryError)) ? (
            <div role="alert" className="picker-feedback">
              <p>{scope !== 'explore' && libraryError || error}</p>
              <button type="button" onClick={() => libraryError && scope !== 'explore' ? setLibraryRetry(n => n + 1) : setRetry(n => n + 1)}>Retry loading</button>
            </div>
          ) : loading || search !== debouncedSearch ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 'var(--workspace-space-8)', padding: 'var(--workspace-space-24)', color: '#555e68', fontSize: 'var(--workspace-font-control)',
            }}>
              <Loader2 size={16} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
              Loading...
            </div>
          ) : items.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: "var(--workspace-space-24) var(--workspace-space-12)", color: '#555e68', fontSize: 'var(--workspace-font-control)',
            }}>
              {debouncedSearch
                ? `No ${kindPlural} matching "${debouncedSearch}"`
                : scope === 'mine'
                  ? `No ${kindPlural} saved in your library yet.`
                  : scope === 'team'
                    ? `No team ${kindPlural} found.`
                    : `No ${kindPlural} shared with everyone yet.`
              }
              <p className="wizard-field-help">{debouncedSearch ? 'Clear your search or try another scope.' : 'Try another scope to find an action.'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
              {items.map(item => {
                const isSelected = item.id === currentId
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={isSelected}
                    className="action-picker-item"
                    onClick={() => onSelect(item.id, item.name)}
                    style={{
                      display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-12)',
                      padding: "var(--workspace-space-12) var(--workspace-space-12)", textAlign: 'left', width: '100%',
                      backgroundColor: isSelected ? '#f7f4e8' : '#fff',
                      border: isSelected ? '1.5px solid var(--highlight-on-light, #806600)' : '1.5px solid transparent',
                      borderRadius: 'var(--workspace-radius-medium)', cursor: 'pointer', fontFamily: 'inherit',
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
                      width: 32, height: 32, borderRadius: 'var(--workspace-radius-medium)', flexShrink: 0,
                      backgroundColor: kind === 'workflow' ? '#ede9fe' : '#f7f4e8',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginTop: 1,
                    }}>
                      {kind === 'workflow'
                        ? <Workflow size={16} style={{ color: '#7c3aed' }} />
                        : <FileText size={16} style={{ color: 'var(--highlight-on-light, #806600)' }} />
                      }
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', minWidth: 0 }}>
                        <div style={{
                          fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: '#111827',
                          overflowWrap: 'anywhere',
                        }}>
                          {item.name}
                        </div>
                        {item.pinned && (
                          <span title="Pinned" style={{ display: 'inline-flex', flexShrink: 0 }}>
                            <Pin size={12} style={{ color: 'var(--library-highlight, #eab308)' }} aria-label="Pinned" />
                          </span>
                        )}
                        {item.favorited && (
                          <span title="Favorited" style={{ display: 'inline-flex', flexShrink: 0 }}>
                            <Star size={12} fill="#fbbc04" style={{ color: '#fbbc04' }} aria-label="Favorited" />
                          </span>
                        )}
                      </div>
                      {item.description && (
                        <div style={{
                          fontSize: 'var(--workspace-font-meta)', color: '#555e68', marginTop: 'var(--workspace-space-2)',
                          overflowWrap: 'anywhere',
                        }}>
                          {item.description}
                        </div>
                      )}
                    </div>
                    {item.qualityTier && tierColors[item.qualityTier] && (
                      <span style={{
                        fontSize: 'var(--workspace-font-meta)', fontWeight: 600, padding: "var(--workspace-space-2) var(--workspace-space-8)",
                        borderRadius: 'var(--workspace-radius-large)', textTransform: 'uppercase', flexShrink: 0,
                        backgroundColor: tierColors[item.qualityTier].bg,
                        color: tierColors[item.qualityTier].text,
                      }}>
                        {item.qualityTier}
                      </span>
                    )}
                    {isSelected && (
                      <span style={{
                        fontSize: 'var(--workspace-font-meta)', fontWeight: 600, padding: "var(--workspace-space-2) var(--workspace-space-8)",
                        borderRadius: 'var(--workspace-radius-large)', backgroundColor: '#f7f4e8', color: '#554400',
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
      </FocusTrap>
    </div>
  )
}
