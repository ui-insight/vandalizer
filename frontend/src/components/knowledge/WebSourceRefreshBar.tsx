import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { refreshKBWebSources, updateKnowledgeBase } from '../../api/knowledge'
import type { KnowledgeBaseSource, URLRefreshInterval } from '../../types/knowledge'
import { formatCurrencyDate } from './sourceCurrency'

/** When a web source's page was last successfully looked at. */
function lastChecked(s: KnowledgeBaseSource): string | null {
  return s.currency?.last_retrieved_at ?? s.currency?.content_retrieved_at ?? null
}

/**
 * The oldest web source's last successful retrieval — how current the
 * knowledge base is, as far as its web pages go. `never` when any web source
 * has never been retrieved.
 */
export function oldestRetrieval(sources: KnowledgeBaseSource[]): string | 'never' | null {
  const web = sources.filter(s => s.source_type === 'url')
  if (!web.length) return null
  let oldest: string | null = null
  for (const s of web) {
    const at = lastChecked(s)
    if (!at) return 'never'
    if (!oldest || at < oldest) oldest = at
  }
  return oldest
}

/**
 * One line above a KB's sources: how current its web sources are, a way to
 * re-fetch them all, and whether they re-fetch on their own. Shown only when
 * the KB has web sources. Each refresh is the per-source Refresh — a failed
 * fetch keeps the previous text.
 */
export function WebSourceRefreshBar({
  kbUuid, sources, interval, canManage, onChanged, onError,
}: {
  kbUuid: string
  sources: KnowledgeBaseSource[]
  interval: URLRefreshInterval | null | undefined
  canManage: boolean
  /** Reload the KB after a change; `message` is a toast to show. */
  onChanged: (message?: string) => void
  onError: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const webCount = sources.filter(s => s.source_type === 'url').length
  if (!webCount) return null
  const oldest = oldestRetrieval(sources)
  const oldestText = oldest === 'never'
    ? 'some not yet retrieved'
    : oldest ? `oldest retrieved ${formatCurrencyDate(oldest)}` : null

  const refreshAll = async () => {
    setBusy(true)
    try {
      const r = await refreshKBWebSources(kbUuid)
      onChanged(
        r.queued
          ? `Re-fetching ${r.queued} web page${r.queued === 1 ? '' : 's'} in background. Previous text is kept if a fetch fails.`
          : 'Every web source is already being refreshed.',
      )
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to refresh web sources')
    } finally {
      setBusy(false)
    }
  }

  const setInterval_ = async (value: string) => {
    try {
      await updateKnowledgeBase(kbUuid, { url_refresh_interval: value as 'off' | URLRefreshInterval })
      onChanged(value === 'off' ? 'Automatic refresh turned off' : `Web sources will refresh ${value}`)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save the refresh setting')
    }
  }

  return (
    <div
      data-testid="web-source-refresh-bar"
      style={{
        display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8,
        padding: '6px 8px', marginBottom: 8, borderRadius: 6,
        backgroundColor: '#262626', border: '1px solid #333', fontSize: 11, color: '#aaa',
      }}
    >
      <span style={{ flex: 1, minWidth: 140 }}>
        {webCount} web source{webCount === 1 ? '' : 's'}{oldestText ? ` · ${oldestText}` : ''}
      </span>
      <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        Auto-refresh
        <select
          aria-label="Refresh web sources automatically"
          value={interval ?? 'off'}
          disabled={!canManage}
          onChange={e => setInterval_(e.target.value)}
          style={{
            fontSize: 11, fontFamily: 'inherit', padding: '2px 4px', borderRadius: 4,
            backgroundColor: '#1e1e1e', color: '#ddd', border: '1px solid #3a3a3a',
          }}
        >
          <option value="off">Off</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </label>
      {canManage && (
        <button
          type="button"
          onClick={refreshAll}
          disabled={busy}
          style={{
            display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontFamily: 'inherit',
            padding: '3px 8px', borderRadius: 4, cursor: busy ? 'default' : 'pointer',
            backgroundColor: 'transparent', color: '#ddd', border: '1px solid #3a3a3a',
          }}
        >
          <RefreshCw size={11} style={busy ? { animation: 'spin 1s linear infinite' } : undefined} />
          Refresh all
        </button>
      )}
    </div>
  )
}
