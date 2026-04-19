import { useState, useEffect, useMemo } from 'react'
import { Check, ChevronRight, Edit2, SkipForward, X, CheckCircle2, Loader2 } from 'lucide-react'
import {
  cancelVerificationSession,
  finalizeVerificationSession,
  patchVerificationField,
  type VerificationSession,
} from '../../api/verificationSessions'

interface VerificationNavBarProps {
  session: VerificationSession
  onSessionUpdated: (session: VerificationSession) => void
  onCompleted: (outcome: {
    session: VerificationSession
    testCaseUuid: string | null
    outcome: 'finalized' | 'cancelled'
  }) => void
  onActiveValueChange: (value: string) => void
}

export function VerificationNavBar({
  session,
  onSessionUpdated,
  onCompleted,
  onActiveValueChange,
}: VerificationNavBarProps) {
  // Index of the current field under review. Advance to the first pending
  // field automatically so a returning user lands on their next unresolved item.
  const firstPendingIdx = useMemo(() => {
    const idx = session.fields.findIndex((f) => f.status === 'pending')
    return idx === -1 ? 0 : idx
  }, [session.uuid])

  const [index, setIndex] = useState(firstPendingIdx)
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [busy, setBusy] = useState(false)

  const total = session.fields.length
  const resolvedCount = session.fields.filter((f) => f.status !== 'pending').length
  const current = session.fields[index]

  // Whenever the active field changes, push its extracted value up so the PDF
  // highlighter shows only that term (one value at a time keeps focus tight).
  useEffect(() => {
    if (current) onActiveValueChange(current.extracted)
  }, [current?.key, current?.extracted])

  useEffect(() => {
    setEditing(false)
    setEditValue(current?.extracted ?? '')
  }, [current?.key])

  if (!current) return null

  const canGoPrev = index > 0
  const canGoNext = index < total - 1
  const allResolved = session.fields.every((f) => f.status !== 'pending')

  const patch = async (status: 'approved' | 'corrected' | 'skipped', expected?: string) => {
    setBusy(true)
    try {
      const updated = await patchVerificationField(session.uuid, current.key, {
        status,
        expected,
      })
      onSessionUpdated(updated)
      // Auto-advance to the next pending field
      const nextPending = updated.fields.findIndex(
        (f, i) => i > index && f.status === 'pending',
      )
      if (nextPending >= 0) setIndex(nextPending)
      else if (canGoNext) setIndex(index + 1)
    } finally {
      setBusy(false)
    }
  }

  const finalize = async () => {
    setBusy(true)
    try {
      const res = await finalizeVerificationSession(session.uuid)
      onCompleted({
        session: res.session,
        testCaseUuid: res.test_case.uuid,
        outcome: 'finalized',
      })
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    setBusy(true)
    try {
      const updated = await cancelVerificationSession(session.uuid)
      onCompleted({ session: updated, testCaseUuid: null, outcome: 'cancelled' })
    } finally {
      setBusy(false)
    }
  }

  const statusLabel: Record<string, { text: string; color: string }> = {
    pending: { text: 'Pending review', color: '#6b7280' },
    approved: { text: 'Approved', color: '#16a34a' },
    corrected: { text: 'Corrected', color: '#2563eb' },
    skipped: { text: 'Skipped', color: '#9ca3af' },
  }
  const currentStatus = statusLabel[current.status] || statusLabel.pending

  return (
    <div
      style={{
        position: 'sticky',
        bottom: 12,
        left: 0,
        right: 0,
        margin: '0 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: 10,
        borderRadius: 12,
        border: '1px solid #fde68a',
        backdropFilter: 'blur(12px)',
        backgroundColor: 'rgba(255,251,235,0.95)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
        zIndex: 100,
      }}
    >
      {/* Progress row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#6b7280' }}>
        <span style={{ fontWeight: 600, color: '#92400e' }}>
          Verifying: {session.label || session.document_title}
        </span>
        <span style={{ flex: 1 }} />
        <span>
          {resolvedCount} / {total} resolved
        </span>
        <button
          onClick={cancel}
          disabled={busy}
          style={navBtn}
          title="Cancel verification"
          aria-label="Cancel verification"
        >
          <X size={14} />
        </button>
      </div>

      {/* Field under review */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 8px',
          borderRadius: 8,
          background: '#fff',
          border: '1px solid #fef3c7',
          fontSize: 13,
        }}
      >
        <button
          onClick={() => canGoPrev && setIndex(index - 1)}
          disabled={!canGoPrev || busy}
          style={navBtn}
          aria-label="Previous field"
          title="Previous field"
        >
          ‹
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: '#9ca3af', fontSize: 11, fontWeight: 500 }}>
            {current.key}
            <span style={{ marginLeft: 8, color: currentStatus.color }}>
              · {currentStatus.text}
            </span>
          </div>
          {editing ? (
            <input
              autoFocus
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && editValue.trim()) {
                  patch('corrected', editValue.trim())
                  setEditing(false)
                } else if (e.key === 'Escape') {
                  setEditing(false)
                }
              }}
              style={{
                width: '100%',
                padding: '3px 6px',
                border: '1px solid #3b82f6',
                borderRadius: 4,
                fontSize: 13,
                outline: 'none',
              }}
            />
          ) : (
            <div
              style={{
                color: '#374151',
                fontWeight: 500,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={current.extracted}
            >
              {current.expected && current.status === 'corrected' ? (
                <>
                  <span style={{ textDecoration: 'line-through', color: '#9ca3af', marginRight: 6 }}>
                    {current.extracted}
                  </span>
                  <span>{current.expected}</span>
                </>
              ) : (
                current.extracted || <span style={{ color: '#d1d5db' }}>(empty)</span>
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => canGoNext && setIndex(index + 1)}
          disabled={!canGoNext || busy}
          style={navBtn}
          aria-label="Next field"
          title="Next field"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      {/* Action row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {!editing && (
          <>
            <button
              onClick={() => patch('approved')}
              disabled={busy}
              style={{ ...actionBtn, background: '#16a34a', color: '#fff', borderColor: '#16a34a' }}
              title="Looks right — approve this value"
            >
              {busy ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
              Looks right
            </button>
            <button
              onClick={() => {
                setEditValue(current.extracted)
                setEditing(true)
              }}
              disabled={busy}
              style={actionBtn}
              title="Correct this value"
            >
              <Edit2 size={13} />
              Correct
            </button>
            <button
              onClick={() => patch('skipped')}
              disabled={busy}
              style={actionBtn}
              title="Can't confirm from this document — skip"
            >
              <SkipForward size={13} />
              Skip
            </button>
          </>
        )}
        {editing && (
          <>
            <button
              onClick={() => {
                if (editValue.trim()) {
                  patch('corrected', editValue.trim())
                  setEditing(false)
                }
              }}
              disabled={busy || !editValue.trim()}
              style={{ ...actionBtn, background: '#2563eb', color: '#fff', borderColor: '#2563eb' }}
            >
              Save correction
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={busy}
              style={actionBtn}
            >
              Cancel
            </button>
          </>
        )}

        <span style={{ flex: 1 }} />

        <button
          onClick={finalize}
          disabled={busy || !allResolved}
          style={{
            ...actionBtn,
            background: allResolved ? '#92400e' : '#fde68a',
            color: allResolved ? '#fff' : '#92400e',
            borderColor: allResolved ? '#92400e' : '#fde68a',
            cursor: allResolved ? 'pointer' : 'not-allowed',
          }}
          title={
            allResolved
              ? 'Lock these values in as a test case'
              : 'Resolve every field first (approve, correct, or skip)'
          }
        >
          <CheckCircle2 size={14} />
          Lock in test case
        </button>
      </div>
    </div>
  )
}

const navBtn: React.CSSProperties = {
  width: 28,
  height: 28,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
  color: '#6b7280',
  borderRadius: 4,
}

const actionBtn: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '5px 10px',
  border: '1px solid #d1d5db',
  background: '#fff',
  color: '#374151',
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  fontFamily: 'inherit',
  transition: 'all 0.15s',
}
