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
        'group relative flex cursor-pointer flex-col items-center gap-1 rounded-[var(--ui-radius)] border-2 border-dashed',
        dragOver
          ? 'border-[var(--highlight-color,#eab308)] bg-[var(--highlight-color,#eab308)]/[0.06] scale-[1.01]'
          : 'border-[#17181a30] hover:border-[#17181a60] hover:bg-[#17181a06]',
      )}
      style={{
        height: 100, margin: '30px 0', justifyContent: 'center',
        transition: 'border-color 0.2s, background-color 0.2s, transform 0.2s',
      }}
    >
      <CloudUpload
        className="h-6 w-6 transition-transform duration-200 group-hover:scale-110"
        style={{ color: dragOver ? 'var(--highlight-color, #eab308)' : '#17181abb' }}
      />
      <div style={{
        fontSize: 14, fontWeight: 500, padding: '0 15px', textAlign: 'center',
        color: dragOver ? 'var(--highlight-color, #eab308)' : '#17181abb',
        transition: 'color 0.2s',
      }}>
        {dragOver ? 'Drop files here' : 'Drag & Drop to Upload Files'}
      </div>
      <div style={{ fontSize: 12, fontWeight: 300, color: '#5d5d5d78' }}>
        <i>pdf, xls, xlsx, csv, docx</i>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.xlsx,.xls,.csv"
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFilesSelected(e.target.files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
