import { useCallback, useEffect, useState } from 'react'
import { Search, Plus, Pencil, Trash2, UserCircle, X, Users } from 'lucide-react'
import {
  listGroups, createGroup, updateGroup, deleteGroup,
  listGroupMembers, addGroupMember, removeGroupMember,
  searchUsersForGroup,
} from '../../api/library'
import type { Group, GroupMember } from '../../types/library'

export function GroupManager() {
  const [groups, setGroups] = useState<Group[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null)

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)

  // Edit form
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [saving, setSaving] = useState(false)

  // Members
  const [members, setMembers] = useState<GroupMember[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ user_id: string; name: string | null; email: string | null }[]>([])
  const [searching, setSearching] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listGroups()
      setGroups(data.groups)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const loadMembers = useCallback(async (group: Group) => {
    setMembersLoading(true)
    try {
      const data = await listGroupMembers(group.uuid)
      setMembers(data.members)
    } catch {
      setMembers([])
    } finally {
      setMembersLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedGroup) {
      loadMembers(selectedGroup)
    }
  }, [selectedGroup, loadMembers])

  // Search users with debounce
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }
    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await searchUsersForGroup(searchQuery.trim())
        setSearchResults(data.users)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      await createGroup({ name: newName.trim(), description: newDesc.trim() || undefined })
      setNewName('')
      setNewDesc('')
      setShowCreate(false)
      refresh()
    } finally {
      setCreating(false)
    }
  }

  const handleUpdate = async () => {
    if (!editingGroup) return
    setSaving(true)
    try {
      await updateGroup(editingGroup.uuid, {
        name: editName.trim() || undefined,
        description: editDesc.trim() || undefined,
      })
      setEditingGroup(null)
      refresh()
      if (selectedGroup?.uuid === editingGroup.uuid) {
        setSelectedGroup(prev => prev ? { ...prev, name: editName.trim() || prev.name, description: editDesc.trim() || prev.description } : null)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (group: Group) => {
    if (!confirm(`Delete group "${group.name}"? This will remove it from all items and knowledge bases.`)) return
    await deleteGroup(group.uuid)
    if (selectedGroup?.uuid === group.uuid) setSelectedGroup(null)
    refresh()
  }

  const handleAddMember = async (userId: string) => {
    if (!selectedGroup) return
    await addGroupMember(selectedGroup.uuid, userId)
    loadMembers(selectedGroup)
    refresh()
  }

  const handleRemoveMember = async (userId: string) => {
    if (!selectedGroup) return
    await removeGroupMember(selectedGroup.uuid, userId)
    loadMembers(selectedGroup)
    refresh()
  }

  const memberUserIds = new Set(members.map(m => m.user_id))

  return (
    <div>
      {/* Group list + create */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700">
            Groups ({groups.length})
          </h3>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-gray-900 text-white hover:bg-gray-800"
          >
            <Plus className="h-3.5 w-3.5" />
            Create Group
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="border border-gray-200 rounded-lg bg-white p-4 mb-4 max-w-md">
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  placeholder="e.g. Legal Dept"
                  className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Description (optional)</label>
                <input
                  type="text"
                  value={newDesc}
                  onChange={e => setNewDesc(e.target.value)}
                  placeholder="Brief description..."
                  className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setShowCreate(false); setNewName(''); setNewDesc('') }}
                  className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="px-3 py-1.5 text-xs font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Edit modal */}
        {editingGroup && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
                <h3 className="text-base font-semibold text-gray-900">Edit Group</h3>
                <button onClick={() => setEditingGroup(null)} className="p-1 rounded hover:bg-gray-100 text-gray-500">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <input
                    type="text"
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-200">
                <button
                  onClick={() => setEditingGroup(null)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpdate}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Group cards */}
        {loading ? (
          <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
        ) : groups.length === 0 ? (
          <div className="text-sm text-gray-500 py-8 text-center border border-gray-200 rounded-lg bg-white">
            No groups created yet. Groups restrict who can see verified items and knowledge bases.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {groups.map(group => (
              <div
                key={group.uuid}
                onClick={() => setSelectedGroup(group)}
                className={`border rounded-lg p-4 bg-white cursor-pointer transition-colors ${
                  selectedGroup?.uuid === group.uuid
                    ? 'border-gray-900 ring-1 ring-gray-900'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-gray-900 truncate">{group.name}</div>
                    {group.description && (
                      <div className="text-xs text-gray-500 mt-1 line-clamp-2">{group.description}</div>
                    )}
                    <div className="flex items-center gap-1 mt-2 text-xs text-gray-500">
                      <Users className="h-3 w-3" />
                      {group.member_count ?? 0} member{(group.member_count ?? 0) !== 1 ? 's' : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => { setEditingGroup(group); setEditName(group.name); setEditDesc(group.description || '') }}
                      className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                      title="Edit"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(group)}
                      className="p-1.5 rounded hover:bg-red-50 text-red-500"
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Members section */}
      {selectedGroup && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Members of &ldquo;{selectedGroup.name}&rdquo;
          </h3>

          {/* Search users to add */}
          <div className="mb-4">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search users to add..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>

            {searchQuery.trim() && (
              <div className="mt-2 border border-gray-200 rounded-lg bg-white max-w-md">
                {searching ? (
                  <div className="text-xs text-gray-500 py-4 text-center">Searching...</div>
                ) : searchResults.length === 0 ? (
                  <div className="text-xs text-gray-500 py-4 text-center">No users found.</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {searchResults.map(user => {
                      const isMember = memberUserIds.has(user.user_id)
                      return (
                        <div key={user.user_id} className="flex items-center justify-between px-4 py-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <UserCircle className="h-5 w-5 text-gray-400 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-gray-900 truncate">{user.name || 'Unknown'}</div>
                              <div className="text-xs text-gray-500 truncate">{user.email || user.user_id}</div>
                            </div>
                          </div>
                          {isMember ? (
                            <span className="text-xs text-gray-400 shrink-0">Already member</span>
                          ) : (
                            <button
                              onClick={() => handleAddMember(user.user_id)}
                              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-green-50 text-green-700 border border-green-200 hover:bg-green-100 shrink-0"
                            >
                              <Plus className="h-3.5 w-3.5" />
                              Add
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Member list */}
          {membersLoading ? (
            <div className="text-sm text-gray-500 py-8 text-center">Loading members...</div>
          ) : members.length === 0 ? (
            <div className="text-sm text-gray-500 py-8 text-center border border-gray-200 rounded-lg bg-white">
              No members yet. Use the search above to add users to this group.
            </div>
          ) : (
            <div className="border border-gray-200 rounded-lg bg-white divide-y divide-gray-100">
              {members.map(member => (
                <div key={member.user_id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <UserCircle className="h-5 w-5 text-gray-400 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">{member.name || 'Unknown'}</div>
                      <div className="text-xs text-gray-500 truncate">{member.email || member.user_id}</div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemoveMember(member.user_id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
