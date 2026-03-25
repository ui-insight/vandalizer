import type { SurveyField } from '../../types/demo'

const INPUT_CLASS =
  'w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50'

const LIKERT_LABELS = ['Strongly Disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly Agree']

interface Props {
  field: SurveyField
  value: unknown
  onChange: (key: string, value: unknown) => void
}

export function SurveyFieldRenderer({ field, value, onChange }: Props) {
  switch (field.type) {
    case 'text':
      return (
        <input
          type="text"
          required={field.required}
          value={(value as string) || ''}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className={INPUT_CLASS}
        />
      )

    case 'number':
      return (
        <input
          type="number"
          required={field.required}
          value={(value as string) || ''}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          min="0"
          className={INPUT_CLASS}
        />
      )

    case 'textarea':
      return (
        <textarea
          required={field.required}
          value={(value as string) || ''}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          className={`${INPUT_CLASS} resize-none`}
        />
      )

    case 'select':
      return (
        <select
          required={field.required}
          value={(value as string) || ''}
          onChange={(e) => onChange(field.key, e.target.value)}
          className={`${INPUT_CLASS} [&>option]:text-black`}
        >
          <option value="">Select...</option>
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )

    case 'multiselect': {
      const selected = (value as string[]) || []
      return (
        <div className="space-y-2">
          {field.options?.map((opt) => (
            <label key={opt} className="flex items-center gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...selected, opt]
                    : selected.filter((s) => s !== opt)
                  onChange(field.key, next)
                }}
                className="w-4 h-4 rounded border-white/20 bg-white/5 text-[#f1b300] focus:ring-[#f1b300]/50"
              />
              <span className="text-sm text-gray-300 group-hover:text-white transition-colors">
                {opt}
              </span>
            </label>
          ))}
        </div>
      )
    }

    case 'likert_group': {
      const ratings = (value as Record<string, string>) || {}
      return (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-left text-gray-400 font-medium pb-3 pr-4 min-w-[200px]" />
                {LIKERT_LABELS.map((label, i) => (
                  <th
                    key={i}
                    className="text-center text-gray-400 font-medium pb-3 px-2 min-w-[60px] text-xs"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {field.statements?.map((stmt) => (
                <tr key={stmt.key} className="border-t border-white/5">
                  <td className="py-3 pr-4 text-gray-300 text-sm leading-snug">
                    {stmt.label}
                  </td>
                  {LIKERT_LABELS.map((_, i) => (
                    <td key={i} className="py-3 text-center">
                      <input
                        type="radio"
                        name={`${field.key}_${stmt.key}`}
                        value={String(i + 1)}
                        checked={ratings[stmt.key] === String(i + 1)}
                        onChange={() => {
                          onChange(field.key, { ...ratings, [stmt.key]: String(i + 1) })
                        }}
                        className="w-4 h-4 border-white/20 bg-white/5 text-[#f1b300] focus:ring-[#f1b300]/50"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    case 'info':
      return (
        <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">
          {field.label}
        </p>
      )

    default:
      return null
  }
}
