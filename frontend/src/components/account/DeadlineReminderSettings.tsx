import { useEffect, useRef, useState } from 'react'
import { BellRing } from 'lucide-react'
import { getReminderSettings, updateReminderSettings, type ReminderSettings } from '../../api/obligations'

// Choices for "remind me before the due date". Each is one reminder; a
// deadline added late gets only the reminders still ahead of it.
const DAY_CHOICES = [30, 14, 7, 3, 1]

/** Account settings for deadline reminders: the bell, email, timing, weekly summary. */
export function DeadlineReminderSettings() {
  const [settings, setSettings] = useState<ReminderSettings | null>(null)
  const [teamAdmin, setTeamAdmin] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pending = useRef(false)

  useEffect(() => {
    getReminderSettings()
      .then(data => { setSettings(data.settings); setTeamAdmin(data.team_admin) })
      .catch(() => setError('Could not load your reminder settings.'))
  }, [])

  const save = async (changes: Partial<ReminderSettings>) => {
    if (!settings || pending.current) return
    pending.current = true
    const previous = settings
    setSettings({ ...settings, ...changes }); setSaving(true); setError(null)
    try {
      const saved = await updateReminderSettings(changes)
      setSettings(saved.settings); setTeamAdmin(saved.team_admin)
    } catch (reason) {
      setSettings(previous)
      setError(`${reason instanceof Error ? reason.message : 'The setting could not be saved.'} Your saved settings were restored.`)
    } finally { pending.current = false; setSaving(false) }
  }

  const toggleDay = (day: number) => {
    if (!settings) return
    const days = settings.days_before.includes(day)
      ? settings.days_before.filter(d => d !== day)
      : [...settings.days_before, day].sort((a, b) => b - a)
    void save({ days_before: days })
  }

  const option = (key: keyof ReminderSettings, label: string, hint: string) => settings && (
    <label className="flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={settings[key] as boolean}
        disabled={saving}
        onChange={() => void save({ [key]: !settings[key] })}
        className="mt-1 h-4 w-4 rounded border-gray-300 text-highlight focus:ring-highlight"
      />
      <div className="flex-1">
        <div className="text-sm font-medium text-gray-900">{label}</div>
        <div className="text-xs text-gray-500">{hint}</div>
      </div>
    </label>
  )

  const off = settings != null && !settings.bell && !settings.email

  return (
    <div id="deadline-reminders" className="rounded-lg border border-gray-200 bg-white scroll-mt-4">
      <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
        <BellRing className="h-4 w-4 text-gray-600" />
        <h3 className="font-medium text-gray-900">Deadline reminders</h3>
        {saving && <span className="ml-auto text-xs text-gray-600">Saving...</span>}
      </div>
      <div className="p-4 space-y-4">
        <p className="text-sm text-gray-600">
          Reminders for deadlines in your projects' RA inbox, each linking to the item and the passage it came from.
          Recurring deadlines are reminded for every occurrence. Marking an item done stops its reminders for everyone.
        </p>
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        {!settings ? (error ? null : <p role="status" className="text-sm text-gray-600">Loading...</p>) : <>
          <div className="space-y-3">
            {option('bell', 'Notification bell', 'Reminders and overdue alerts in the bell at the top of the app.')}
            {option('email', 'Email', 'The same reminders by email, sent together when several are due.')}
          </div>
          <fieldset disabled={off || saving} className="space-y-2 disabled:opacity-60">
            <legend className="text-sm font-medium text-gray-900">Remind me</legend>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Days before the due date">
              {DAY_CHOICES.map(day => {
                const on = settings.days_before.includes(day)
                return <button key={day} type="button" aria-pressed={on} onClick={() => toggleDay(day)}
                  className={`rounded-full border px-3 py-1 text-xs ${on ? 'border-amber-500 bg-amber-50 text-amber-900' : 'border-gray-300 text-gray-700'}`}>
                  {day} day{day === 1 ? '' : 's'} before
                </button>
              })}
            </div>
            {option('on_due', 'On the due date', 'A reminder the morning a deadline is due.')}
            {option('overdue', 'When a deadline passes', "An alert once a deadline's date has passed and it isn't marked done.")}
          </fieldset>
          {option('weekly_summary', 'Weekly summary email', 'Mondays: overdue, due this week and the next 30 days across your projects.')}
          {teamAdmin && option('team_projects', "Your teams' projects", "As a team admin, also get reminders for every project of your teams, not only the ones you own or that are shared with you.")}
        </>}
      </div>
    </div>
  )
}
