import { createPortal as nativeCreatePortal } from 'react-dom'
import type { ReactNode } from 'react'
import { PanelPortalVisibility } from './PanelVisibility'

export function createPortal(children: ReactNode, container: Element | DocumentFragment, key?: string | null) {
  return nativeCreatePortal(<PanelPortalVisibility>{children}</PanelPortalVisibility>, container, key)
}
