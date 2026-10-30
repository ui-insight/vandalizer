/** Dispatch a custom event to open the support chat panel from anywhere. */
export function openSupportPanel(ticketUuid?: string) {
  window.dispatchEvent(new CustomEvent('open-support-panel', { detail: { ticketUuid } }))
}

export interface SupportDraftContext {
  key: string
  subject: string
  message: string
}

/** Open an editable draft. Only the support form's Submit action sends it. */
export function openSupportDraft(draft: SupportDraftContext) {
  window.dispatchEvent(new CustomEvent('open-support-panel', { detail: { draft } }))
}
