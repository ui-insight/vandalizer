import { useLayoutEffect, useRef, useState } from 'react'

/** One outer scroll, while authored HTML remains isolated from the application. */
export function PublishedPageContent({ src }: { src: string }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    const resize = (event: MessageEvent) => {
      if (!frame.current?.contentWindow || event.source !== frame.current.contentWindow) return
      const data: unknown = event.data
      if (!data || typeof data !== 'object' || !('type' in data) || data.type !== 'vandalizer:page-height'
        || !('height' in data) || typeof data.height !== 'number' || !Number.isFinite(data.height)
        || data.height < 1 || data.height > 1_000_000) return
      setHeight(Math.ceil(data.height))
    }
    window.addEventListener('message', resize)
    return () => window.removeEventListener('message', resize)
  }, [])
  const url = `${src}${src.includes('?') ? '&' : '?'}view=embed`
  return <iframe ref={frame} className="page-published-content" title="Published page content" src={url}
    sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
    style={height ? { height } : undefined} />
}
