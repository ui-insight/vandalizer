import { useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import { getInbox, setInboxHidden } from '../../api/obligations'

/** Account setting for the RA inbox on Home (#999): the way back after "Hide inbox". */
export function HomeInboxSetting() {
  const [hidden, setHidden] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getInbox().then(data => setHidden(data.inbox_hidden)).catch(() => setError('Could not load this setting.'))
  }, [])

  const toggle = async () => {
    if (hidden == null || saving) return
    setSaving(true)
    setError(null)
    try {
      setHidden((await setInboxHidden(!hidden)).inbox_hidden)
    } catch {
      setError('The setting could not be saved. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
        <Inbox className="h-4 w-4 text-gray-600" />
        <h3 className="font-medium text-gray-900">Home</h3>
      </div>
      <div className="p-4 space-y-2">
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={hidden === false}
            disabled={hidden == null || saving}
            onChange={toggle}
            className="mt-1 h-4 w-4 rounded border-gray-300 text-highlight focus:ring-highlight"
          />
          <div className="flex-1">
            <div className="text-sm font-medium text-gray-900">Show the RA inbox on Home</div>
            <div className="text-xs text-gray-500">
              Deadlines, missing material and sponsor-limit conflicts from your projects' documents, each linked to its page.
              Turning it off only changes your Home; your projects keep every item.
            </div>
          </div>
          {saving && <span className="text-xs text-gray-600">Saving...</span>}
        </label>
      </div>
    </div>
  )
}
