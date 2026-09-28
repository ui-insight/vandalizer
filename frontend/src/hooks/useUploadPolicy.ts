import { useEffect, useState } from 'react'
import { FALLBACK_UPLOAD_POLICY, readUploadPolicy } from '../utils/uploadPolicy'

export function useUploadPolicy() {
  const [policy, setPolicy] = useState(FALLBACK_UPLOAD_POLICY)
  useEffect(() => {
    let cancelled = false
    void readUploadPolicy().then(value => { if (!cancelled) setPolicy(value) })
    return () => { cancelled = true }
  }, [])
  return { policy, accept: policy.extensions.map(ext => `.${ext}`).join(','),
    description: `${policy.extensions.join(', ')} · ${policy.max_size_bytes == null ? 'Size limit unavailable; uploads are checked by the server.' : `Up to ${policy.max_size_bytes / (1024 * 1024)} MB per file.`}` }
}
