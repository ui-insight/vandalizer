import { Component, type ComponentPropsWithoutRef, type RefObject } from 'react'

type Props = ComponentPropsWithoutRef<'div'> & {
  scrollRef: RefObject<HTMLDivElement | null>
  isStreaming: boolean
  conversationUuid: string | null
}

/** Keep the reader's position across streamed DOM replacements. */
export class ChatScrollRegion extends Component<Props> {
  // A scroll event may still be queued when the next token renders. Capture
  // the actual position before React changes the DOM, not a cached event value
  // or a layout effect (which runs after content can already have collapsed).
  getSnapshotBeforeUpdate(previous: Props): number | null {
    const el = this.props.scrollRef.current
    if ((!previous.isStreaming && !this.props.isStreaming)
      || previous.conversationUuid !== this.props.conversationUuid
      || !el || el.offsetParent === null) return null
    return el.scrollTop
  }

  componentDidUpdate(_previous: Props, _state: unknown, top: number | null) {
    const el = this.props.scrollRef.current
    if (top !== null && el && el.offsetParent !== null && el.scrollTop !== top) {
      el.scrollTop = top
    }
  }

  render() {
    const { scrollRef, isStreaming: _isStreaming, conversationUuid: _conversationUuid, style, ...props } = this.props
    // The browser must not independently anchor to markdown nodes that are
    // replaced on every delta. Explicit navigation still controls scrollTop.
    return <div {...props} ref={scrollRef} style={{ ...style, overflowAnchor: 'none' }} />
  }
}
