import { useCallback, useEffect, useRef, useState } from 'react'

/** A changed filter or a manual retry invalidates earlier responses and exports. */
export function useAdminQuery<T>(request: () => Promise<T>) {
  const version = useRef(0)
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    const current = ++version.current
    setLoading(true)
    setError(null)
    setData(null)
    request().then(result => {
      if (version.current === current) setData(result)
    }).catch(reason => {
      if (version.current === current) setError(reason instanceof Error ? reason.message : 'Unable to load records. Please retry.')
    }).finally(() => {
      if (version.current === current) setLoading(false)
    })
  }, [request])
  useEffect(() => {
    const guard = version
    load()
    return () => { guard.current++ }
  }, [load])
  return { data, setData, loading, error, load }
}
