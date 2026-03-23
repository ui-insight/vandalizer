import { ShieldCheck, Tag, Pencil, Trash2, Bookmark, BookmarkCheck, Copy, MessageSquare } from 'lucide-react'
import type { KnowledgeBase } from '../../types/knowledge'
import type { Organization } from '../../api/organizations'

const STATUS_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  empty: { label: 'Empty', color: '#6b7280', bg: '#f3f4f6' },
  building: { label: 'Building', color: '#d97706', bg: '#fef3c7' },
  ready: { label: 'Ready', color: '#15803d', bg: '#dcfce7' },
  error: { label: 'Error', color: '#b91c1c', bg: '#fef2f2' },
}

interface KBCardProps {
  kb: KnowledgeBase
  allOrgs: Organization[]
  onSelect: (uuid: string) => void
  onChat: (uuid: string, title: string) => void
  onEdit?: (uuid: string) => void
  onDelete?: (uuid: string) => void
  onAdopt?: (uuid: string) => void
  onRemoveRef?: (refUuid: string) => void
  onClone?: (uuid: string) => void
  onExplore?: (kb: KnowledgeBase) => void
}

export function KBCard({
  kb, allOrgs, onSelect, onChat, onEdit, onDelete, onAdopt, onRemoveRef, onClone, onExplore,
}: KBCardProps) {
  const badge = STATUS_BADGE[kb.status] || STATUS_BADGE.empty
  const isReady = kb.status === 'ready'
  const isReference = kb.is_reference

  return (
    <button
      onClick={() => onExplore ? onExplore(kb) : (isReady ? onChat(isReference ? kb.source_kb_uuid! : kb.uuid, kb.title) : onSelect(kb.uuid))}
      style={{
        display: 'block', width: '100%', textAlign: 'left',
        padding: '14px 16px', backgroundColor: '#2a2a2a',
        border: isReference ? '1px solid rgba(37, 99, 235, 0.3)' : '1px solid #3a3a3a',
        borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
        transition: 'background-color 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#333')}
      onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
    >
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        {isReference && (
          <BookmarkCheck size={13} style={{ color: '#2563eb', flexShrink: 0 }} />
        )}
        <span style={{
          fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {kb.title}
        </span>
        {kb.shared_with_team && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
            color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
            whiteSpace: 'nowrap',
          }}>
            Team
          </span>
        )}
        {kb.verified && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
            color: '#15803d', backgroundColor: '#dcfce7',
            display: 'flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap',
          }}>
            <ShieldCheck size={10} />
            Verified
          </span>
        )}
        <span style={{
          fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          color: badge.color, backgroundColor: badge.bg,
        }}>
          {badge.label}
        </span>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#999' }}>
        <span>{kb.total_sources} sources</span>
        <span>{kb.total_chunks} chunks</span>
      </div>

      {/* Org badges */}
      {(kb.organization_ids?.length ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
          {kb.organization_ids.map(gid => {
            const o = allOrgs.find(x => x.uuid === gid)
            return (
              <span key={gid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
              }}>
                <Tag size={9} />
                {o?.name || gid}
              </span>
            )
          })}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
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
              border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
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
              color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
              border: '1px solid rgba(37, 99, 235, 0.2)', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Bookmark size={11} />
            Add to My KBs
          </button>
        )}
        {onClone && (
          <button
            onClick={(e) => { e.stopPropagation(); onClone(kb.uuid) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: '#ccc', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Copy size={11} />
            Clone
          </button>
        )}
        {isReference && onRemoveRef && kb.reference_uuid && (
          <button
            onClick={(e) => { e.stopPropagation(); onRemoveRef(kb.reference_uuid!) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 8px', fontSize: 11, fontFamily: 'inherit',
              color: '#888', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Trash2 size={11} />
            Remove
          </button>
        )}
        {onDelete && !isReference && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(kb.uuid) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 8px', fontSize: 11, fontFamily: 'inherit',
              color: '#888', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <Trash2 size={11} />
          </button>
        )}
      </div>
    </button>
  )
}
