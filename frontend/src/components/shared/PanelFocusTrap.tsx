import { useRef, type ComponentProps } from 'react'
import { FocusTrap as NativeFocusTrap } from 'focus-trap-react'
import { usePanelVisible } from './PanelVisibility'

/** Hidden retained panels must neither capture nor restore keyboard focus. */
export function FocusTrap(props: ComponentProps<typeof NativeFocusTrap>) {
  const visible = usePanelVisible()
  const visibleRef = useRef(visible)
  visibleRef.current = visible
  const options = props.focusTrapOptions
  return <NativeFocusTrap {...props} active={visible && props.active !== false} focusTrapOptions={{
    ...options,
    setReturnFocus: previous => {
      if (!visibleRef.current) return false
      const target = options?.setReturnFocus
      return typeof target === 'function' ? target(previous) : target ?? previous
    },
  }} />
}
