import { useState } from 'react'
import { X } from 'lucide-react'

interface AddUrlsModalProps {
  onSubmit: (urls: string[]) => void
  onClose: () => void
}

export function AddUrlsModal({ onSubmit, onClose }: AddUrlsModalProps) {
  const [text, setText] = useState('')

  const handleSubmit = () => {
    const urls = text
      .split('\n')
      .map(u => u.trim())
      .filter(u => u.length > 0)
    if (urls.length > 0) {
      onSubmit(urls)
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 480, maxHeight: '80vh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: '1px solid #3a3a3a', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add URLs</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>
        <div style={{ fontSize: 13, color: '#aaa' }}>
          Paste one URL per line. Each URL will be fetched, its text extracted, and added to the knowledge base.
        </div>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={'https://example.com/page1\nhttps://example.com/page2'}
          rows={8}
          style={{
            width: '100%', padding: 12, fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', color: '#e5e5e5',
            border: '1px solid #3a3a3a', borderRadius: 8,
            resize: 'vertical', outline: 'none',
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
              color: '#ccc', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!text.trim()}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: '#000', backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 6,
              cursor: text.trim() ? 'pointer' : 'default',
              opacity: text.trim() ? 1 : 0.5,
            }}
          >
            Add URLs
          </button>
        </div>
      </div>
    </div>
  )
}
