/** Dispatch a custom event to open the support chat panel from anywhere. */
export function openSupportPanel(ticketUuid?: string) {
  window.dispatchEvent(new CustomEvent('open-support-panel', { detail: { ticketUuid } }))
}
