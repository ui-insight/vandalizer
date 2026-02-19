import { useCallback, useEffect, useState } from 'react'
import { getBreadcrumbs } from '../api/folders'

export function useBreadcrumbs(folderId: string | null) {
  const [breadcrumbs, setBreadcrumbs] = useState<Array<{ uuid: string; title: string }>>([])

  const refresh = useCallback(async () => {
    if (!folderId || folderId === '0') {
      setBreadcrumbs([])
      return
    }
    const crumbs = await getBreadcrumbs(folderId)
    setBreadcrumbs(crumbs)
  }, [folderId])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { breadcrumbs, refresh }
}
