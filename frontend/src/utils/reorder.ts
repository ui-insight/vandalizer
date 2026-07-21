// Compute a new id order for a drag-and-drop reorder: move dragId so it sits
// before/after targetId. Returns null when the move is invalid or a no-op
// (callers skip the API call in that case).
export function computeReorderedIds(
  ids: string[],
  dragId: string,
  targetId: string,
  position: 'before' | 'after',
): string[] | null {
  if (dragId === targetId) return null
  const next = [...ids]
  const from = next.indexOf(dragId)
  if (from === -1) return null
  next.splice(from, 1)
  const targetIdx = next.indexOf(targetId)
  if (targetIdx === -1) return null
  next.splice(position === 'after' ? targetIdx + 1 : targetIdx, 0, dragId)
  if (next.every((id, i) => id === ids[i])) return null
  return next
}
