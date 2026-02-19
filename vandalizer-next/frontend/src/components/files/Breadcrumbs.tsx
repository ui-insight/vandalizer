interface BreadcrumbsProps {
  items: Array<{ uuid: string; title: string }>
  onNavigate: (folderId: string | null) => void
}

export function Breadcrumbs({ items, onNavigate }: BreadcrumbsProps) {
  return (
    <nav
      className="overflow-x-auto whitespace-nowrap"
      style={{ padding: '20px 30px 0px 0px' }}
    >
      <ol className="inline-flex items-center gap-1 list-none m-0 p-0">
        <li className="inline-flex items-center text-sm" style={{ fontWeight: 200 }}>
          <button
            onClick={() => onNavigate(null)}
            className="bg-transparent border-0 cursor-pointer p-0"
            style={{ color: '#c6c6c6', textDecoration: 'none' }}
          >
            Home
          </button>
        </li>
        {items.map((item) => (
          <li key={item.uuid} className="inline-flex items-center text-sm" style={{ fontWeight: 200 }}>
            <span className="mx-[7.5px] opacity-60" aria-hidden="true">›</span>
            <button
              onClick={() => onNavigate(item.uuid)}
              className="bg-transparent border-0 cursor-pointer p-0"
              style={{ color: '#a2a2a2', fontWeight: 300 }}
            >
              {item.title}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  )
}
