import { MessageCircleQuestion, X } from 'lucide-react'
import type { PendingPrompt } from '../../api/feedbackPrompt'

interface Props {
  prompt: PendingPrompt
  onRespond: () => void
  onDismiss: () => void
  onClose: () => void
}

export function FeedbackPromptCard({ prompt, onRespond, onDismiss, onClose }: Props) {
  return (
    <div
      role="dialog"
      aria-label="Trial check-in"
      className="fixed z-40 w-[340px] rounded-xl border border-amber-200 bg-white shadow-[0_10px_30px_rgba(0,0,0,0.12)]"
      style={{ top: 85, right: 24 }}
    >
      <div className="flex items-start gap-2.5 rounded-t-xl bg-amber-50 px-4 py-2.5">
        <MessageCircleQuestion className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <div className="flex-1 text-[11px] font-bold uppercase tracking-wider text-amber-700">
          Quick check-in
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-amber-700/60 transition-colors hover:text-amber-900"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="px-4 py-3">
        <div className="mb-1.5 text-sm font-semibold text-gray-900">{prompt.subject}</div>
        <p className="text-[13px] leading-relaxed text-gray-600">{prompt.question_text}</p>
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-4 py-2.5">
        <button
          onClick={onDismiss}
          className="rounded-md px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        >
          Don't show again
        </button>
        <button
          onClick={onRespond}
          className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-600"
        >
          Respond
        </button>
      </div>
    </div>
  )
}
