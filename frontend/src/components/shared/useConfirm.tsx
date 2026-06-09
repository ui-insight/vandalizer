import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { ConfirmDialog } from './ConfirmDialog'

interface ConfirmOptions {
  title?: string
  message: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

interface DialogState extends ConfirmOptions {
  open: boolean
  resolve?: (value: boolean) => void
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState>({ open: false, message: '' })

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      setState({ ...opts, open: true, resolve })
    })
  }, [])

  const handleCancel = useCallback(() => {
    state.resolve?.(false)
    setState((s) => ({ ...s, open: false, resolve: undefined }))
  }, [state])

  const handleConfirm = useCallback(async () => {
    state.resolve?.(true)
    setState((s) => ({ ...s, open: false, resolve: undefined }))
  }, [state])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <ConfirmDialog
        open={state.open}
        title={state.title}
        message={state.message}
        confirmLabel={state.confirmLabel}
        cancelLabel={state.cancelLabel}
        destructive={state.destructive}
        onCancel={handleCancel}
        onConfirm={handleConfirm}
      />
    </ConfirmContext.Provider>
  )
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext)
  if (!ctx) {
    throw new Error('useConfirm must be used within a ConfirmProvider')
  }
  return ctx
}
