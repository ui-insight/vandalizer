export function InventoryPages({ offset, count, total, hasMore, busy, onChange, pageSize = 500 }: {
  offset: number; count: number; total?: number; hasMore: boolean; busy: boolean; onChange: (offset: number) => void; pageSize?: number
}) {
  return <div className="admin-pagination">
    <p role="status">{busy ? 'Loading records…' : `${count ? offset + 1 : 0}–${offset + count}${total === undefined ? '' : ` of ${total}`} records. Filters, sorting and export cover this page.`}</p>
    <button type="button" disabled={busy || offset === 0} onClick={() => onChange(Math.max(0, offset - pageSize))}>Previous page</button>
    <button type="button" disabled={busy || !hasMore} onClick={() => onChange(offset + pageSize)}>Next page</button>
  </div>
}
