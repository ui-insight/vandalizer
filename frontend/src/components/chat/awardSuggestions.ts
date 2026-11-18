// Suggestions offered when a selected document looks like an award.
//
// Vandalizer has no document type, so this goes by the file's name: a notice
// of award, an award letter, a subaward or a grant agreement. A miss only
// hides a suggestion; the person can still ask.

export const LIST_PRIOR_APPROVALS = 'List prior approvals'

const AWARD_NAME = /(?:^|[^a-z])(?:noa|nga|award|subaward|sub-award|subcontract|notice of (?:grant )?award|grant agreement|cooperative agreement)(?:[^a-z]|$)/i

export function looksLikeAward(name: string | undefined): boolean {
  return !!name && AWARD_NAME.test(name.replace(/[_.-]+/g, ' '))
}
