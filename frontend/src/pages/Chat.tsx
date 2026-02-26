import { useEffect, useState, useCallback } from 'react'
import { MessageSquare, Plus, Trash2, Clock } from 'lucide-react'
import { AppLayout } from '../components/layout/AppLayout'
import { ChatPanel } from '../components/chat/ChatPanel'
import { listConversations, deleteHistory } from '../api/chat'
import type { ConversationSummary } from '../api/chat'

export function Chat() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [activeConvo, setActiveConvo] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const loadConversations = useCallback(() => {
    listConversations(100)
      .then(setConversations)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadConversations() }, [loadConversations])

  const handleNewChat = () => {
    setActiveConvo(null)
  }

  const handleSelectConvo = (uuid: string) => {
    setActiveConvo(uuid)
  }

  const handleDeleteConvo = async (uuid: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this conversation?')) return
    await deleteHistory(uuid)
    setConversations(prev => prev.filter(c => c.uuid !== uuid))
    if (activeConvo === uuid) setActiveConvo(null)
  }

  const formatRelativeDate = (d: string | null) => {
    if (!d) return ''
    const diff = Date.now() - new Date(d).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    if (days < 7) return `${days}d ago`
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <AppLayout>
      <div style={{ display: 'flex', height: '100%' }}>
        {/* Conversation sidebar */}
        {!sidebarCollapsed && (
          <div style={{
            width: 280, borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column',
            backgroundColor: '#f9fafb', flexShrink: 0,
          }}>
            {/* Sidebar header */}
            <div style={{
              padding: '12px 16px', borderBottom: '1px solid #e5e7eb',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>Conversations</span>
              <button
                onClick={handleNewChat}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px',
                  borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                  fontSize: 12, fontWeight: 600, cursor: 'pointer', background: '#fff',
                }}
              >
                <Plus size={14} /> New
              </button>
            </div>

            {/* Conversation list */}
            <div style={{ flex: 1, overflow: 'auto', padding: '8px 8px' }}>
              {loading ? (
                <div style={{ padding: 20, textAlign: 'center', fontSize: 13, color: '#9ca3af' }}>Loading...</div>
              ) : conversations.length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', fontSize: 13, color: '#9ca3af' }}>
                  No conversations yet. Start a new chat!
                </div>
              ) : (
                conversations.map(c => (
                  <button
                    key={c.uuid}
                    onClick={() => handleSelectConvo(c.uuid)}
                    style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%',
                      padding: '10px 12px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                      background: activeConvo === c.uuid ? '#e5e7eb' : 'transparent',
                      cursor: 'pointer', textAlign: 'left', marginBottom: 2,
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => { if (activeConvo !== c.uuid) e.currentTarget.style.background = '#f3f4f6' }}
                    onMouseLeave={e => { if (activeConvo !== c.uuid) e.currentTarget.style.background = 'transparent' }}
                  >
                    <MessageSquare size={16} style={{ color: '#9ca3af', marginTop: 2, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 500, color: '#111827',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {c.title || 'Untitled'}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>
                          {c.message_count} msg{c.message_count !== 1 ? 's' : ''}
                        </span>
                        <span style={{ fontSize: 11, color: '#d1d5db' }}>·</span>
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>
                          {formatRelativeDate(c.updated_at || c.created_at)}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => handleDeleteConvo(c.uuid, e)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer', padding: 4,
                        color: '#d1d5db', flexShrink: 0, marginTop: 0,
                        opacity: 0.5, transition: 'opacity 0.15s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.color = '#ef4444' }}
                      onMouseLeave={e => { e.currentTarget.style.opacity = '0.5'; e.currentTarget.style.color = '#d1d5db' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {/* Chat panel */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <ChatPanel
            key={activeConvo || 'new'}
            conversationToLoad={activeConvo}
          />
        </div>
      </div>
    </AppLayout>
  )
}

export default Chat
