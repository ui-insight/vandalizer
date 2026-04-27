import { ArrowLeft } from 'lucide-react'

interface BreadcrumbsProps {
  items: Array<{ uuid: string; title: string }>
  onNavigate: (folderId: string | null) => void
}

export function Breadcrumbs({ items, onNavigate }: BreadcrumbsProps) {
  const atRoot = items.length === 0
  const parentId = items.length >= 2 ? items[items.length - 2].uuid : null
  const currentTitle = items.length > 0 ? items[items.length - 1].title : null
  const ancestors = items.slice(0, -1)

  const handleUp = () => {
    if (atRoot) return
    onNavigate(parentId)
  }

  return (
    <nav
      aria-label="Folder navigation"
      className="overflow-x-auto whitespace-nowrap flex items-center gap-2"
      style={{ padding: '20px 30px 0px 0px' }}
    >
      {!atRoot && (
        <button
          type="button"
          onClick={handleUp}
          aria-label="Go to parent folder"
          title="Go to parent folder"
          className="inline-flex items-center justify-center rounded-md border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          style={{ width: 28, height: 28 }}
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      )}

      <ol className="inline-flex items-center gap-1 list-none m-0 p-0">
        <li className="inline-flex items-center text-sm">
          {atRoot ? (
            <span style={{ color: '#111', fontWeight: 600 }}>Home</span>
          ) : (
            <button
              type="button"
              onClick={() => onNavigate(null)}
              className="bg-transparent border-0 cursor-pointer p-0 text-gray-600 hover:text-gray-900 hover:underline"
              style={{ fontWeight: 400 }}
            >
              Home
            </button>
          )}
        </li>
        {ancestors.map((item) => (
          <li key={item.uuid} className="inline-flex items-center text-sm">
            <span className="mx-[7.5px] text-gray-400" aria-hidden="true">›</span>
            <button
              type="button"
              onClick={() => onNavigate(item.uuid)}
              className="bg-transparent border-0 cursor-pointer p-0 text-gray-600 hover:text-gray-900 hover:underline"
              style={{ fontWeight: 400 }}
            >
              {item.title}
            </button>
          </li>
        ))}
        {currentTitle && (
          <li className="inline-flex items-center text-sm" aria-current="page">
            <span className="mx-[7.5px] text-gray-400" aria-hidden="true">›</span>
            <span style={{ color: '#111', fontWeight: 600 }}>{currentTitle}</span>
          </li>
        )}
      </ol>
    </nav>
  )
}
