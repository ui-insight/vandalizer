import { useState } from 'react'
import { AppLayout } from '../components/layout/AppLayout'
import { LibraryList } from '../components/library/LibraryList'
import { LibraryItemsPanel } from '../components/library/LibraryItemsPanel'
import { VerificationQueue } from '../components/library/VerificationQueue'
import { useLibraries } from '../hooks/useLibrary'
import { useAuth } from '../hooks/useAuth'
import type { Library as LibraryType } from '../types/library'

type Tab = 'browse' | 'verification'

export default function Library() {
  const { user } = useAuth()
  const teamId = user?.current_team ?? undefined
  const { libraries, loading } = useLibraries(teamId)
  const [selected, setSelected] = useState<LibraryType | null>(null)
  const [tab, setTab] = useState<Tab>('browse')

  // Auto-select first library when loaded
  const activeLibrary = selected ?? libraries[0] ?? null

  return (
    <AppLayout>
      <div className="flex h-full flex-col -m-6">
        {/* Tab bar */}
        <div className="flex gap-0 border-b border-gray-200 px-6 shrink-0 bg-white">
          {(['browse', 'verification'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 text-sm font-semibold capitalize transition-colors ${
                tab === t
                  ? 'border-b-2 border-gray-900 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex flex-1 min-h-0">
          {tab === 'browse' && (
            <>
              {loading ? (
                <div className="flex-1 flex items-center justify-center text-sm text-gray-500">
                  Loading...
                </div>
              ) : (
                <>
                  <LibraryList
                    libraries={libraries}
                    selectedId={activeLibrary?.id ?? null}
                    onSelect={setSelected}
                  />
                  <div className="flex-1 overflow-auto p-6">
                    {activeLibrary ? (
                      <LibraryItemsPanel library={activeLibrary} teamId={teamId} />
                    ) : (
                      <div className="flex items-center justify-center h-full text-sm text-gray-500">
                        No libraries found. They will be created automatically.
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {tab === 'verification' && (
            <div className="flex-1 overflow-auto p-6">
              <VerificationQueue />
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
