/**
 * Map an in-message action button (`[ACTION:type]Label[/ACTION]`, rendered by
 * markdown.ts into `<button data-action="type">Label</button>`) to what a click
 * should do.
 *
 * Only two action types have dedicated behavior. The markdown renderer, though,
 * turns ANY `[ACTION:type]` the model emits into a real, styled button — so
 * unrecognized types (e.g. `create-kb`, `build-workflow`) must not dead-end.
 * They fall back to sending the button's own label as a chat message, which
 * lets the assistant perform the action via its tools.
 *
 * Pure so the routing is unit-testable in isolation from ChatMessage.
 */
export type ActionRoute =
  | { kind: 'cert' }
  | { kind: 'files' }
  | { kind: 'send'; message: string }
  | { kind: 'none' }

export function routeActionClick(action: string | null, label: string): ActionRoute {
  if (action === 'start-cert') return { kind: 'cert' }
  if (action === 'upload-docs') return { kind: 'files' }
  if (action) {
    const trimmed = label.trim()
    return trimmed ? { kind: 'send', message: trimmed } : { kind: 'none' }
  }
  return { kind: 'none' }
}
