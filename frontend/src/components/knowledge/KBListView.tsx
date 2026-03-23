import { Loader2 } from 'lucide-react'
import { useScopedKnowledgeBases } from '../../hooks/useKnowledgeBases'
import type { KBScope } from '../../types/knowledge'
import type { Organization } from '../../api/organizations'
import { KBCard } from './KBCard'

interface KBListViewProps {
  scope: KBScope
  search: string
  allOrgs: Organization[]
  onSelect: (uuid: string) => void
  onChat: (uuid: string, title: string) => void
  onEdit?: (uuid: string) => void
  onDelete?: (uuid: string) => void
  onAdopt?: (uuid: string) => void
  onRemoveRef?: (refUuid: string) => void
  onClone?: (uuid: string) => void
  emptyMessage?: string
}

export function KBListView({
  scope, search, allOrgs,
  onSelect, onChat, onEdit, onDelete, onAdopt, onRemoveRef, onClone,
  emptyMessage = 'No knowledge bases found.',
}: KBListViewProps) {
  const { knowledgeBases, loading } = useScopedKnowledgeBases({
    scope,
    search: search || undefined,
  })

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
        <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (knowledgeBases.length === 0) {
    return (
      <div style={{ fontSize: 13, color: '#888', textAlign: 'center', padding: '40px 20px' }}>
        {emptyMessage}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {knowledgeBases.map(kb => (
        <KBCard
          key={kb.is_reference ? `ref-${kb.reference_uuid}` : kb.uuid}
          kb={kb}
          allOrgs={allOrgs}
          onSelect={onSelect}
          onChat={onChat}
          onEdit={onEdit}
          onDelete={onDelete}
          onAdopt={onAdopt}
          onRemoveRef={onRemoveRef}
          onClone={onClone}
        />
      ))}
    </div>
  )
}
