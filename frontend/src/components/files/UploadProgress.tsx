import { CheckCircle, AlertCircle } from 'lucide-react'

interface UploadItem {
  fileName: string
  progress: number
  done: boolean
  error?: string
}

export function UploadProgress({ uploads }: { uploads: UploadItem[] }) {
  if (uploads.length === 0) return null

  return (
    <div className="space-y-2">
      {uploads.map((u, i) => (
        <div key={i} role="status" aria-live="polite" className="flex items-center gap-3 rounded-md bg-white p-3 shadow-sm">
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">{u.fileName}</span>
              {u.done && !u.error && (
                <>
                  <CheckCircle aria-hidden="true" className="h-4 w-4 text-green-500" />
                  <span className="sr-only">Upload complete</span>
                </>
              )}
              {u.error && (
                <>
                  <AlertCircle aria-hidden="true" className="h-4 w-4 text-red-500" />
                  <span className="sr-only">Upload failed</span>
                </>
              )}
            </div>
            {!u.done && (
              <div
                className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-200"
                role="progressbar"
                aria-valuenow={Math.round(u.progress)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Uploading ${u.fileName}`}
              >
                <div
                  className="h-full rounded-full bg-highlight transition-all"
                  style={{ width: `${u.progress}%` }}
                />
              </div>
            )}
            {u.error && <p className="mt-1 text-xs text-red-600">{u.error}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}
