import { useCallback, useEffect, useState } from 'react'
import { Search, ShieldCheck, ShieldOff, UserCircle } from 'lucide-react'
import { listExaminers, setExaminer, searchUsersForExaminer } from '../../api/library'
import type { ExaminerUser } from '../../types/library'

export function ExaminerManager() {
  const [examiners, setExaminers] = useState<ExaminerUser[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ExaminerUser[]>([])
  const [searching, setSearching] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listExaminers()
      setExaminers(data.examiners)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Search users with debounce
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }
    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await searchUsersForExaminer(searchQuery.trim())
        setSearchResults(data.users)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const handleToggle = async (userId: string, makeExaminer: boolean) => {
    setToggling(userId)
    try {
      await setExaminer(userId, makeExaminer)
      refresh()
      // Update search results in place
      setSearchResults(prev => prev.map(u =>
        u.user_id === userId ? { ...u, is_examiner: makeExaminer } : u
      ))
    } finally {
      setToggling(null)
    }
  }

  return (
    <div>
      {/* Search users */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">Search Users</label>
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
          />
        </div>

        {/* Search results */}
        {searchQuery.trim() && (
          <div className="mt-2 border border-gray-200 rounded-lg bg-white max-w-md">
            {searching ? (
              <div className="text-xs text-gray-500 py-4 text-center">Searching...</div>
            ) : searchResults.length === 0 ? (
              <div className="text-xs text-gray-500 py-4 text-center">No users found.</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {searchResults.map((user) => (
                  <div key={user.user_id} className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <UserCircle className="h-5 w-5 text-gray-400 shrink-0" />
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900 truncate">{user.name || 'Unknown'}</div>
                        <div className="text-xs text-gray-500 truncate">{user.email || user.user_id}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleToggle(user.user_id, !user.is_examiner)}
                      disabled={toggling === user.user_id}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors shrink-0 ${
                        user.is_examiner
                          ? 'bg-red-50 text-red-700 border border-red-200 hover:bg-red-100'
                          : 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100'
                      } disabled:opacity-50`}
                    >
                      {user.is_examiner ? (
                        <>
                          <ShieldOff className="h-3.5 w-3.5" />
                          Revoke
                        </>
                      ) : (
                        <>
                          <ShieldCheck className="h-3.5 w-3.5" />
                          Grant
                        </>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Current examiners list */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Current Examiners ({examiners.length})
        </h3>
        {loading ? (
          <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
        ) : examiners.length === 0 ? (
          <div className="text-sm text-gray-500 py-8 text-center border border-gray-200 rounded-lg bg-white">
            No examiners configured. Use the search above to grant examiner access.
          </div>
        ) : (
          <div className="border border-gray-200 rounded-lg bg-white divide-y divide-gray-100">
            {examiners.map((user) => (
              <div key={user.user_id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-green-50 flex items-center justify-center shrink-0">
                    <ShieldCheck className="h-4 w-4 text-green-600" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{user.name || 'Unknown'}</div>
                    <div className="text-xs text-gray-500 truncate">{user.email || user.user_id}</div>
                  </div>
                </div>
                <button
                  onClick={() => handleToggle(user.user_id, false)}
                  disabled={toggling === user.user_id}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50 shrink-0"
                >
                  <ShieldOff className="h-3.5 w-3.5" />
                  Revoke
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
