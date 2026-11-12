import type { ReactNode } from 'react'
import { PageDialog } from './PagePrimitives'

export function PageDeleteDialog({ title, busy, feedback, onClose, onConfirm }: {
  title: string; busy: boolean; feedback?: ReactNode; onClose: () => void; onConfirm: () => void
}) {
  return <PageDialog title="Delete this page?" busy={busy} onClose={onClose}>
    <p>This deletes every saved version of <strong>{title}</strong> and removes all its public links. This cannot be undone.</p>
    {feedback}
    <div className="page-actions"><button className="page-button" disabled={busy} autoFocus onClick={onClose}>Keep page</button><button className="page-button page-button-danger" disabled={busy} onClick={onConfirm}>Delete permanently</button></div>
  </PageDialog>
}
