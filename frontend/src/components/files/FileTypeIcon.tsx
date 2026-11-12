import { File, FileCode, FileImage, FileSpreadsheet, FileText, FileType, Presentation, type LucideIcon } from 'lucide-react'
import { fileKind, type FileKind } from '../../utils/fileDisplay'

// Shape and colour both differ per kind, so the type reads without relying on
// colour alone.
const ICONS: Record<FileKind, { icon: LucideIcon; color: string; label: string }> = {
  pdf: { icon: FileType, color: '#b42318', label: 'PDF' },
  document: { icon: FileText, color: '#1d4ed8', label: 'Document' },
  spreadsheet: { icon: FileSpreadsheet, color: '#15803d', label: 'Spreadsheet' },
  presentation: { icon: Presentation, color: '#c2410c', label: 'Presentation' },
  image: { icon: FileImage, color: '#7e22ce', label: 'Image' },
  web: { icon: FileCode, color: '#0f766e', label: 'Web page' },
  other: { icon: File, color: '#6b7280', label: 'File' },
}

export function FileTypeIcon({ extension, className = 'h-4 w-4 shrink-0 mr-2.5' }: { extension: string | null | undefined; className?: string }) {
  const kind = fileKind(extension)
  const { icon: Icon, color, label } = ICONS[kind]
  return (
    <span className="inline-flex shrink-0" title={label} data-file-kind={kind}>
      <Icon className={className} style={{ color }} aria-hidden="true" />
    </span>
  )
}
