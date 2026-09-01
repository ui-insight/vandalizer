import { useEffect, useMemo, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { BookOpen, Check, Loader2, Search, X } from 'lucide-react'
import { listKnowledgeBasesV2 } from '../../api/knowledge'
import type { KnowledgeBase, KBScope } from '../../types/knowledge'

/**
 * Attach knowledge bases to the current chat.
 *
 * The "Add Knowledge Base" item in the chat's + menu used to switch the
 * workspace to the Knowledge panel, leaving the user to find the KB and press
 * "Chat with this KB" — which also replaced the conversation. This attaches in
 * place, several at a time, without leaving the chat.
 */

const SCOPES: { value: KBScope; label: string }[] = [
  { value: 'mine', label: 'Mine' },
  { value: 'team', label: 'Team' },
  { value: 'verified', label: 'Verified' },
]

interface Props {
  attachedUuids: string[]
  maxAttached: number
  onAttach: (kbs: { uuid: string; title: string }[]) => void
  onClose: () => void
}

export function AttachKBModal({ attachedUuids, maxAttached, onAttach, onClose }: Props) {
  const [scope, setScope] = useState<KBScope>('mine')
  const [kbs, setKbs] = useState<KnowledgeBase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<Record<string, string>>({})

  useEffect(() => {
    let cancelled = false
    setKbs(null)
    setError(null)
    listKnowledgeBasesV2({ scope, limit: 100 })
      .then(res => {
        if (cancelled) return
        // A broken bookmark ('unavailable') has no KB behind it to retrieve from.
        setKbs(res.items.filter(kb => kb.status !== 'unavailable'))
      })
      .catch(() => { if (!cancelled) setError('Could not load knowledge bases.') })
    return () => { cancelled = true }
  }, [scope])

  const pickedCount = Object.keys(picked).length
  const remaining = maxAttached - attachedUuids.length - pickedCount

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return kbs || []
    return (kbs || []).filter(kb => kb.title.toLowerCase().includes(q))
  }, [kbs, search])

  const toggle = (kb: KnowledgeBase) => {
    setPicked(prev => {
      if (prev[kb.uuid]) {
        const next = { ...prev }
        delete next[kb.uuid]
        return next
      }
      if (remaining <= 0) return prev
      return { ...prev, [kb.uuid]: kb.title }
    })
  }

  const confirm = () => {
    onAttach(Object.entries(picked).map(([uuid, title]) => ({ uuid, title })))
    onClose()
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 900 }}
      onKeyDown={e => { if (e.key === 'Escape') onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="attach-kb-title"
          className="flex w-full max-w-md flex-col rounded-lg bg-white shadow-xl"
          style={{ maxHeight: '70vh' }}
        >
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
            <h3 id="attach-kb-title" className="text-base font-medium text-gray-900">
              Attach knowledge bases
            </h3>
            <button type="button" onClick={onClose} aria-label="Close" className="text-gray-500 hover:text-gray-700">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="px-5 pt-3">
            <p className="text-xs text-gray-500">
              Chat can search up to {maxAttached} knowledge bases at once, alongside any
              documents you have selected.
              {remaining <= 0 && ' You have reached the limit — detach one to add another.'}
            </p>
            <div className="mt-3 flex gap-1">
              {SCOPES.map(s => (
                <button
                  key={s.value}
                  type="button"
                  aria-pressed={scope === s.value}
                  onClick={() => setScope(s.value)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    scope === s.value ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
              <input
                aria-label="Search knowledge bases"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search knowledge bases"
                className="w-full rounded-md border border-gray-300 py-2 pl-8 pr-3 text-sm"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-3" style={{ minHeight: 120 }}>
            {error ? (
              <p className="text-sm text-red-700">{error}</p>
            ) : kbs === null ? (
              <div className="flex justify-center py-6 text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : visible.length === 0 ? (
              <p className="py-6 text-center text-sm text-gray-500">
                {search ? 'No knowledge base matches that.' : 'No knowledge bases here yet.'}
              </p>
            ) : (
              <ul className="flex flex-col gap-1">
                {visible.map(kb => {
                  const already = attachedUuids.includes(kb.uuid)
                  const selected = !!picked[kb.uuid]
                  const blocked = !already && !selected && remaining <= 0
                  return (
                    <li key={kb.uuid}>
                      <button
                        type="button"
                        disabled={already || blocked}
                        aria-pressed={selected}
                        onClick={() => toggle(kb)}
                        className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left text-sm hover:bg-black/[.04] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <BookOpen className="h-4 w-4 shrink-0 text-gray-400" />
                        <span className="flex-1 truncate text-gray-900">{kb.title}</span>
                        {already ? (
                          <span className="shrink-0 text-xs text-gray-500">attached</span>
                        ) : selected ? (
                          <Check className="h-4 w-4 shrink-0 text-green-600" />
                        ) : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-5 py-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-sm text-gray-700 hover:bg-black/[.04]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={pickedCount === 0}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              {pickedCount > 1 ? `Attach ${pickedCount}` : 'Attach'}
            </button>
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
