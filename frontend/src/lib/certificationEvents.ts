import type { ToolResultInfo } from '../types/chat'
import { certificationPayloadIssue } from './certificationPayload'

/** Recognize completed writes, excluding previews, failed and malformed results. */
export function isCertificationWriteResult(result: ToolResultInfo): boolean {
  const data = result.content
  if (!data || typeof data !== 'object' || Array.isArray(data)) return false
  const value = data as Record<string, unknown>
  if (value.error || value.needs_confirmation || ['failed', 'error', 'canceled', 'cancelled'].includes(String(value.status))) return false
  if (certificationPayloadIssue(result.tool_name, data)) return false
  if (typeof value.module_id !== 'string') return false
  switch (result.tool_name) {
    case 'complete_certification_module': return typeof value.total_xp === 'number' && Number.isFinite(value.total_xp)
    case 'submit_certification_assessment': return value.stored === true
    case 'save_certification_position': return value.saved === true && Number.isSafeInteger(value.position_revision) && Number(value.position_revision) > 0
    case 'provision_certification_lab': return Array.isArray(value.provisioned_docs)
    default: return false
  }
}
