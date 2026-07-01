import { useMemo, useState, type ReactNode } from 'react'
import {
  ArrowUpDown, Loader2, BookOpen, ShieldCheck, Sparkles, Tag,
  MessageSquare, Pencil, Trash2, Bookmark, BookmarkCheck, Pin, PinOff,
} from 'lucide-react'
import { useScopedKnowledgeBases } from '../../hooks/useKnowledgeBases'
import type { KBScope, KnowledgeBase } from '../../types/knowledge'
import type { Organization } from '../../api/organizations'
import { AITrustChip } from './AITrustChip'

type SortOption = 'newest' | 'updated' | 'name' | 'sources' | 'chunks'

const SORT_LABEL: Record<SortOption, string> = {
  newest: 'Newest',
  updated: 'Recently Updated',
  name: 'Name A–Z',
  sources: 'Most Sources',
  chunks: 'Most Chunks',
}

const STATUS_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  empty: { label: 'Empty', color: '#6b7280', bg: '#f3f4f6' },
  building: { label: 'Building', color: '#d97706', bg: '#fef3c7' },
  ready: { label: 'Ready', color: '#15803d', bg: '#dcfce7' },
  error: { label: 'Error', color: '#b91c1c', bg: '#fef2f2' },
}

// Dark palette (matches KBExploreTab)
const C = {
  card: '#262626',
  cardHover: '#2f2f2f',
  border: '#3a3a3a',
  text: '#e5e5e5',
  textMuted: '#aaa',
  textDim: '#888',
  textFaint: '#666',
}

function sortKBs(kbs: KnowledgeBase[], sort: SortOption): KnowledgeBase[] {
  const arr = [...kbs]
  switch (sort) {
    case 'name':
      return arr.sort((a, b) => a.title.localeCompare(b.title))
    case 'updated':
      return arr.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
    case 'sources':
      return arr.sort((a, b) => (b.total_sources ?? 0) - (a.total_sources ?? 0))
    case 'chunks':
      return arr.sort((a, b) => (b.total_chunks ?? 0) - (a.total_chunks ?? 0))
    case 'newest':
    default:
      return arr.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }
}

interface KBGridCardProps {
  kb: KnowledgeBase
  allOrgs: Organization[]
  onSelect: (uuid: string) => void
  onChat: (uuid: string, title: string) => void
  onEdit?: (uuid: string) => void
  onDelete?: (uuid: string) => void
  onAdopt?: (uuid: string) => void
  onRemoveRef?: (refUuid: string) => void
  pinned?: boolean
  onTogglePin?: (canonicalUuid: string) => void
}

function KBGridCard({
  kb, allOrgs, onSelect, onChat, onEdit, onDelete, onAdopt, onRemoveRef, pinned, onTogglePin,
}: KBGridCardProps) {
  const badge = STATUS_BADGE[kb.status] || STATUS_BADGE.empty
  const isReady = kb.status === 'ready'
  const isReference = kb.is_reference
  // The id a project pins is the canonical KB uuid — for a reference card that's
  // the original it points at, matching what onChat uses.
  const canonicalUuid = isReference ? (kb.source_kb_uuid || kb.uuid) : kb.uuid

  return (
    <button
      onClick={() => onSelect(kb.uuid)}
      style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left',
        padding: 14, borderRadius: 12,
        backgroundColor: C.card,
        border: isReference ? '1px solid rgba(37, 99, 235, 0.3)' : `1px solid ${C.border}`,
        cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'inherit',
      }}
      onMouseEnter={e => { e.currentTarget.style.backgroundColor = C.cardHover }}
      onMouseLeave={e => { e.currentTarget.style.backgroundColor = C.card }}
    >
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 6 }}>
        {isReference ? (
          <BookmarkCheck size={14} style={{ color: '#60a5fa', flexShrink: 0, marginTop: 2 }} />
        ) : (
          <BookOpen size={14} style={{ color: '#7dd3fc', flexShrink: 0, marginTop: 2 }} />
        )}
        <span style={{
          fontSize: 13, fontWeight: 600, color: C.text, flex: 1, minWidth: 0,
          lineHeight: 1.3,
          overflow: 'hidden', textOverflow: 'ellipsis',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        }}>
          {kb.title}
        </span>
        {onTogglePin && (
          <button
            onClick={(e) => { e.stopPropagation(); onTogglePin(canonicalUuid) }}
            title={pinned ? 'Unpin from this project' : 'Pin to this project'}
            style={{
              flexShrink: 0, display: 'flex', alignItems: 'center', padding: 2,
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: pinned ? 'var(--highlight-color, #eab308)' : '#666',
            }}
          >
            {pinned ? <Pin size={13} fill="currentColor" /> : <PinOff size={13} />}
          </button>
        )}
      </div>

      {/* AI Trust signal — the headline number for "is this KB worth using?". */}
      <div style={{ marginBottom: 8 }}>
        <AITrustChip
          score={kb.last_validation_score}
          baseline={kb.last_validation_baseline_score}
          lift={kb.last_validation_lift}
        />
      </div>

      {/* Badges row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          color: badge.color, backgroundColor: badge.bg,
        }}>
          {badge.label}
        </span>
        {kb.shared_with_team && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
            color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
          }}>
            Team
          </span>
        )}
        {kb.verified && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
            color: '#15803d', backgroundColor: '#dcfce7',
          }}>
            <ShieldCheck size={10} />
            Verified
          </span>
        )}
        {kb.has_optimized_config && (
          <span
            title={
              kb.optimized_config_set_at
                ? `Optimized settings applied ${new Date(kb.optimized_config_set_at).toLocaleDateString()}`
                : 'Optimized settings applied'
            }
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: '#a78bfa', backgroundColor: 'rgba(124, 58, 237, 0.12)',
              border: '1px solid rgba(124, 58, 237, 0.3)',
            }}
          >
            <Sparkles size={10} />
            Optimized
          </span>
        )}
      </div>

      {/* Description */}
      {kb.description ? (
        <p style={{
          fontSize: 12, color: '#bdbdbd', margin: '0 0 8px', lineHeight: 1.4,
          overflow: 'hidden', textOverflow: 'ellipsis',
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
        }}>
          {kb.description}
        </p>
      ) : (
        <p style={{
          fontSize: 11, color: C.textFaint, margin: '0 0 8px', fontStyle: 'italic',
        }}>
          No description yet
        </p>
      )}

      {/* Stats */}
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: C.textFaint, marginBottom: 8 }}>
        <span>{kb.total_sources} source{kb.total_sources !== 1 ? 's' : ''}</span>
        <span>{kb.total_chunks.toLocaleString()} chunk{kb.total_chunks !== 1 ? 's' : ''}</span>
      </div>

      {/* Org badges */}
      {(kb.organization_ids?.length ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
          {kb.organization_ids.map(gid => {
            const o = allOrgs.find(x => x.uuid === gid)
            return (
              <span key={gid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                color: '#60a5fa', backgroundColor: 'rgba(37, 99, 235, 0.12)',
              }}>
                <Tag size={9} />
                {o?.name || gid}
              </span>
            )
          })}
        </div>
      )}

      {/* User tags */}
      {(kb.tags?.length ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
          {kb.tags.map(t => (
            <span key={t} style={{
              fontSize: 10, padding: '1px 6px', borderRadius: 999,
              backgroundColor: 'rgba(255,255,255,0.06)', color: '#c5c5c5',
            }}>
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 'auto', paddingTop: 4 }}>
        {isReady && (
          <button
            onClick={(e) => { e.stopPropagation(); onChat(isReference ? kb.source_kb_uuid! : kb.uuid, kb.title) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--highlight-text-color, #000)',
              backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <MessageSquare size={11} />
            Chat
          </button>
        )}
        {onEdit && !isReference && (
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(kb.uuid) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: '#ccc', backgroundColor: 'transparent',
              border: `1px solid ${C.border}`, borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Pencil size={11} />
            Edit
          </button>
        )}
        {onAdopt && !isReference && (
          <button
            onClick={(e) => { e.stopPropagation(); onAdopt(kb.uuid) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: '#60a5fa', backgroundColor: 'rgba(37, 99, 235, 0.1)',
              border: '1px solid rgba(37, 99, 235, 0.25)', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Bookmark size={11} />
            Add to My KBs
          </button>
        )}
        {isReference && onRemoveRef && kb.reference_uuid && (
          <button
            onClick={(e) => { e.stopPropagation(); onRemoveRef(kb.reference_uuid!) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 8px', fontSize: 11, fontFamily: 'inherit',
              color: C.textDim, backgroundColor: 'transparent',
              border: `1px solid ${C.border}`, borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Trash2 size={11} />
            Remove
          </button>
        )}
        {onDelete && !isReference && (
          <button
            type="button"
            aria-label="Delete knowledge base"
            onClick={(e) => { e.stopPropagation(); onDelete(kb.uuid) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 8px', fontSize: 11, fontFamily: 'inherit',
              color: C.textDim, backgroundColor: 'transparent',
              border: `1px solid ${C.border}`, borderRadius: 4, cursor: 'pointer',
              marginLeft: 'auto',
            }}
          >
            <Trash2 size={11} />
          </button>
        )}
      </div>
    </button>
  )
}

interface KBGridViewProps {
  scope: KBScope
  search: string
  allOrgs: Organization[]
  onSelect: (uuid: string) => void
  onChat: (uuid: string, title: string) => void
  onEdit?: (uuid: string) => void
  onDelete?: (uuid: string) => void
  onAdopt?: (uuid: string) => void
  onRemoveRef?: (refUuid: string) => void
  emptyMessage?: string
  emptyComponent?: ReactNode
  // Project scoping: when set, only KBs whose canonical uuid is in the set are
  // shown. `onTogglePin` renders a pin toggle on each card (and is what flips
  // membership of that set). Both are driven by the active project's pins.
  filterUuids?: Set<string>
  pinnedUuids?: Set<string>
  onTogglePin?: (canonicalUuid: string) => void
}

export function KBGridView({
  scope, search, allOrgs,
  onSelect, onChat, onEdit, onDelete, onAdopt, onRemoveRef,
  emptyMessage = 'No knowledge bases found.',
  emptyComponent,
  filterUuids, pinnedUuids, onTogglePin,
}: KBGridViewProps) {
  const { knowledgeBases, loading } = useScopedKnowledgeBases({
    scope,
    search: search || undefined,
  })
  const [sort, setSort] = useState<SortOption>('newest')

  const canonical = (kb: KnowledgeBase) => (kb.is_reference ? (kb.source_kb_uuid || kb.uuid) : kb.uuid)

  const scopedKBs = useMemo(
    () => (filterUuids ? knowledgeBases.filter(kb => filterUuids.has(canonical(kb))) : knowledgeBases),
    [knowledgeBases, filterUuids],
  )

  const sorted = useMemo(() => sortKBs(scopedKBs, sort), [scopedKBs, sort])

  if (loading) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', padding: '60px 0', color: C.textFaint,
      }}>
        <Loader2 size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
        <p style={{ fontSize: 12, margin: 0 }}>Loading knowledge bases...</p>
      </div>
    )
  }

  if (sorted.length === 0) {
    if (emptyComponent) return <>{emptyComponent}</>
    return (
      <div style={{ textAlign: 'center', padding: '60px 16px' }}>
        <BookOpen size={42} style={{ color: '#404040', margin: '0 auto 12px' }} />
        <p style={{ fontSize: 13, color: C.textDim, margin: 0 }}>{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div>
      {/* Sort */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginBottom: 12 }}>
        <ArrowUpDown size={13} style={{ color: C.textFaint }} />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOption)}
          style={{
            padding: '4px 8px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
            border: `1px solid ${C.border}`, borderRadius: 6,
            backgroundColor: C.card, color: C.textMuted, outline: 'none', cursor: 'pointer',
          }}
        >
          {(Object.keys(SORT_LABEL) as SortOption[]).map(opt => (
            <option key={opt} value={opt}>{SORT_LABEL[opt]}</option>
          ))}
        </select>
      </div>

      {/* Grid */}
      <div style={{
        display: 'grid', gap: 12,
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
      }}>
        {sorted.map(kb => (
          <KBGridCard
            key={kb.is_reference ? `ref-${kb.reference_uuid}` : kb.uuid}
            kb={kb}
            allOrgs={allOrgs}
            onSelect={onSelect}
            onChat={onChat}
            onEdit={onEdit}
            onDelete={onDelete}
            onAdopt={onAdopt}
            onRemoveRef={onRemoveRef}
            pinned={pinnedUuids?.has(kb.is_reference ? (kb.source_kb_uuid || kb.uuid) : kb.uuid)}
            onTogglePin={onTogglePin}
          />
        ))}
      </div>
    </div>
  )
}
