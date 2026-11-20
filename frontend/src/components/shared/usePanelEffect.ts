import { useEffect, type DependencyList, type EffectCallback } from 'react'
import { usePanelVisible } from './PanelVisibility'

/** Suspend document/window keyboard listeners while their retained panel is hidden. */
export function usePanelEffect(effect: EffectCallback, dependencies: DependencyList) {
  const visible = usePanelVisible()
  useEffect(() => {
    if (visible) return effect()
    // The caller supplies its effect dependencies, just as for useEffect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, ...dependencies])
}
