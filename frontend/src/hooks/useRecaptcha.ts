import { useEffect, useCallback, useRef } from 'react'

declare global {
  interface Window {
    grecaptcha?: {
      ready: (cb: () => void) => void
      execute: (siteKey: string, options: { action: string }) => Promise<string>
    }
  }
}

/**
 * Hook to load and execute reCAPTCHA v3.
 * If siteKey is falsy, the script is not loaded and execute() returns undefined.
 */
export function useRecaptcha(siteKey: string | null | undefined) {
  const loaded = useRef(false)

  useEffect(() => {
    if (!siteKey || loaded.current) return
    if (document.querySelector(`script[src*="recaptcha/api.js"]`)) {
      loaded.current = true
      return
    }
    const script = document.createElement('script')
    script.src = `https://www.google.com/recaptcha/api.js?render=${siteKey}`
    script.async = true
    document.head.appendChild(script)
    loaded.current = true
  }, [siteKey])

  const execute = useCallback(
    async (action: string): Promise<string | undefined> => {
      if (!siteKey || !window.grecaptcha) return undefined
      return new Promise((resolve) => {
        window.grecaptcha!.ready(() => {
          window.grecaptcha!.execute(siteKey, { action }).then(resolve)
        })
      })
    },
    [siteKey],
  )

  return { execute }
}
