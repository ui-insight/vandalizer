import { downloadFileUrl } from '../../api/files'

interface DocumentViewerProps {
  docUuid: string
}

export function DocumentViewer({ docUuid }: DocumentViewerProps) {
  return (
    <iframe
      src={downloadFileUrl(docUuid)}
      style={{ width: '100%', height: '100%', border: 'none' }}
      title="Document viewer"
    />
  )
}
