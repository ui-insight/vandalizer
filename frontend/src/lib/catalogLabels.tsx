/**
 * What "submit for verification" actually does: ask to share the item with
 * everyone here, via an examiner's check. One constant so every surface says
 * the same thing.
 */
export const SHARE_LABEL = 'Share with everyone'

export function useShareLabel(): string {
  return SHARE_LABEL
}

/** Inline text version for places that render children rather than take a string prop. */
export function ShareLabel() {
  return <>{SHARE_LABEL}</>
}
