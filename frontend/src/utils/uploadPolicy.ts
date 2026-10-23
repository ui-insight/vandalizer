import { getUploadPolicy, type UploadPolicy } from '../api/files'
import { SUPPORTED_EXTENSIONS } from './fileTypes'

export const FALLBACK_UPLOAD_POLICY: UploadPolicy = { extensions: SUPPORTED_EXTENSIONS, max_size_bytes: null }
export async function readUploadPolicy(): Promise<UploadPolicy> {
  try { return await getUploadPolicy() } catch { return FALLBACK_UPLOAD_POLICY }
}
export function uploadFileError(file: File, policy: UploadPolicy): string | null {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!file.name.includes('.') || !policy.extensions.includes(ext)) return `Unsupported file type${ext ? ` (.${ext})` : ''} — supported: ${policy.extensions.join(', ')}`
  if (policy.max_size_bytes != null && file.size > policy.max_size_bytes) return `This file exceeds the ${policy.max_size_bytes / (1024 * 1024)} MB per-file limit.`
  return null
}
