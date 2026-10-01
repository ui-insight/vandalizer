import { useCallback, useEffect, useRef, useState } from 'react'
import { getBreadcrumbs } from '../api/folders'

export function useBreadcrumbs(folderId: string | null) {
  const [breadcrumbs, setBreadcrumbs] = useState<Array<{ uuid: string; title: string }>>([])
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)

  const refresh = useCallback(async () => {
    const version = ++request.current
    setError(null)
    if (!folderId || folderId === '0') {
      setBreadcrumbs([])
      return
    }
    try {
      const crumbs = await getBreadcrumbs(folderId)
      if (version === request.current) setBreadcrumbs(crumbs)
    } catch (reason) {
      if (version === request.current) {
        setBreadcrumbs([])
        setError(reason instanceof Error ? reason.message : 'Could not load the folder path.')
      }
    }
  }, [folderId])

  useEffect(() => {
    setBreadcrumbs([])
    void refresh()
    return () => { request.current++ }
  }, [refresh])

  return { breadcrumbs, error, refresh }
}
