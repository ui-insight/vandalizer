import { ActionButton } from './ActionButton'
import { usePanelEffect } from './usePanelEffect'
import { useState } from 'react'
import { FocusTrap } from './PanelFocusTrap'
import { AlertTriangle, X, Loader2 } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title?: string
  message: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)

  usePanelEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  const handleConfirm = async () => {
    try {
      setBusy(true)
      await onConfirm()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 1000 }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      {/* Escape + outside-click are handled above; the trap only confines Tab
          focus to the dialog and restores focus to the trigger on close. */}
      <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {destructive && (
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-red-50">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
            )}
            <h3
              id="confirm-dialog-title"
              className="text-lg font-medium text-gray-900"
              style={{ marginTop: destructive ? 6 : 0 }}
            >
              {title}
            </h3>
          </div>
          <ActionButton variant="quiet" iconOnly
            type="button"
            onClick={onCancel}
            disabled={busy}
            aria-label="Close"

          >
            <X className="h-5 w-5" />
          </ActionButton>
        </div>

        <div className="mb-5 text-sm text-gray-600">{message}</div>

        <div className="flex justify-end gap-2">
          <ActionButton variant="secondary"
            type="button"
            onClick={onCancel}
            disabled={busy}

          >
            {cancelLabel}
          </ActionButton>
          <ActionButton variant={destructive ? 'destructive' : 'primary'} aria-busy={busy}
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            autoFocus

          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {confirmLabel}
          </ActionButton>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
