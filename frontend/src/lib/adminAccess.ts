/** Navigation affordances only; the API independently enforces authorization. */
export function adminAccess(user: { is_admin?: boolean; is_staff?: boolean } | null | undefined, team: { role?: string | null } | null | undefined) {
  const isGlobalAdmin = !!user?.is_admin
  const isStaff = !!user?.is_staff
  const isTeamAdmin = team?.role === 'owner' || team?.role === 'admin'
  return { isGlobalAdmin, isStaff, isTeamAdmin, hasAccess: isGlobalAdmin || isStaff || isTeamAdmin,
    label: isGlobalAdmin || isStaff ? 'Admin' : 'Team Admin' }
}
