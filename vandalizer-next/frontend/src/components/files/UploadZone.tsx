import { useCallback, useRef, useState, type DragEvent } from 'react'
import { CloudUpload } from 'lucide-react'
import { cn } from '../../lib/cn'

interface UploadZoneProps {
  onFilesSelected: (files: FileList) => void
}

export function UploadZone({ onFilesSelected }: UploadZoneProps) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      if (e.dataTransfer.files.length > 0) {
        onFilesSelected(e.dataTransfer.files)
      }
    },
    [onFilesSelected],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={cn(
        'relative flex cursor-pointer flex-col items-center gap-1 rounded-[var(--ui-radius)] border-2 border-dashed transition-colors',
        dragOver
          ? 'border-[#17181a9d]'
          : 'border-[#17181a50]',
      )}
      style={{ height: 100, margin: '30px 0', justifyContent: 'center' }}
    >
      <CloudUpload className="h-6 w-6" style={{ color: '#17181abb' }} />
      <div style={{ fontSize: 14, fontWeight: 500, color: '#17181abb', padding: '0 15px', textAlign: 'center' }}>
        Drag &amp; Drop to Upload Files
      </div>
      <div style={{ fontSize: 12, fontWeight: 300, color: '#5d5d5d78' }}>
        <i>pdf, xls, xlsx, docx</i>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFilesSelected(e.target.files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
