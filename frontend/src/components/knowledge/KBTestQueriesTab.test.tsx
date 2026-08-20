import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { KBTestQueriesTab, chunkForBulkDelete, BULK_DELETE_BATCH } from './KBTestQueriesTab'
import type { KBTestQuery } from '../../api/knowledge'

const bulkDeleteKBTestQueries = vi.fn().mockResolvedValue({ deleted: 2 })
const confirmFn = vi.fn().mockResolvedValue(true)
const generateKBTestQueriesAndWait = vi.fn().mockResolvedValue(undefined)

vi.mock('../../api/knowledge', () => ({
  createKBTestQuery: vi.fn(),
  updateKBTestQuery: vi.fn(),
  deleteKBTestQuery: vi.fn(),
  bulkDeleteKBTestQueries: (uuid: string, uuids: string[]) => bulkDeleteKBTestQueries(uuid, uuids),
  generateKBTestQueriesAndWait: (uuid: string, opts: unknown) =>
    generateKBTestQueriesAndWait(uuid, opts),
}))
vi.mock('./GenerateTestQueriesModal', () => ({
  // Stands in for the coverage picker: the tab only cares that onConfirm fires.
  GenerateTestQueriesModal: ({ onConfirm }: { onConfirm: (c: string) => void }) => (
    <button onClick={() => onConfirm('quick')}>confirm-generate</button>
  ),
}))
vi.mock('./ImportTestQueriesModal', () => ({ ImportTestQueriesModal: () => null }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => confirmFn }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))

function q(uuid: string, query: string, auto: boolean): KBTestQuery {
  return {
    uuid,
    query,
    expected_source_labels: [],
    expected_answer_contains: null,
    expected_answer: null,
    category: null,
    notes: null,
    external_id: null,
    auto_generated: auto,
    source_chunk_ids: [],
    last_judged_score: null,
    last_judged_at: null,
    created_at: null,
    updated_at: null,
  }
}

const QUERIES = [
  q('q-1', 'Hand-written question?', false),
  q('q-2', 'Generated question A?', true),
  q('q-3', 'Generated question B?', true),
]

function renderTab(props: Partial<Parameters<typeof KBTestQueriesTab>[0]> = {}) {
  const onChange = vi.fn()
  render(
    <KBTestQueriesTab
      kbUuid="kb-1"
      kbReady
      canManage
      queries={QUERIES}
      onChange={onChange}
      {...props}
    />,
  )
  return { onChange }
}

// Support ticket: KBs accumulate hundreds of imported/auto-generated test
// queries and the tab only offered row-by-row deletion.
describe('KBTestQueriesTab bulk deletion', () => {
  beforeEach(() => {
    bulkDeleteKBTestQueries.mockClear()
    confirmFn.mockClear()
  })

  it('deletes every selected query in one call', async () => {
    const { onChange } = renderTab()

    fireEvent.click(screen.getByRole('checkbox', { name: /Select all/ }))
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(3\)/ }))

    await waitFor(() => expect(bulkDeleteKBTestQueries).toHaveBeenCalledTimes(1))
    expect(bulkDeleteKBTestQueries).toHaveBeenCalledWith('kb-1', ['q-1', 'q-2', 'q-3'])
    expect(confirmFn).toHaveBeenCalled()
    expect(onChange).toHaveBeenCalled()
  })

  it('scopes "select all" to the active author filter', async () => {
    renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Auto-generated (2)' }))
    expect(screen.queryByText('Hand-written question?')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /Select all auto-generated/ }))
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(2\)/ }))

    await waitFor(() =>
      expect(bulkDeleteKBTestQueries).toHaveBeenCalledWith('kb-1', ['q-2', 'q-3']),
    )
  })

  it('does not delete when the confirmation is declined', async () => {
    confirmFn.mockResolvedValueOnce(false)
    renderTab()

    fireEvent.click(screen.getByRole('checkbox', { name: /Select test query: Hand-written/ }))
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(1\)/ }))

    await waitFor(() => expect(confirmFn).toHaveBeenCalled())
    expect(bulkDeleteKBTestQueries).not.toHaveBeenCalled()
  })

  it('hides selection affordances for a view-only user', () => {
    renderTab({ canManage: false })

    expect(screen.queryByRole('checkbox', { name: /Select all/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Select test query/ })).not.toBeInTheDocument()
    // Filtering stays available — it is read-only.
    expect(screen.getByRole('button', { name: 'User-authored (1)' })).toBeInTheDocument()
  })
})


describe('chunkForBulkDelete', () => {
  // The endpoint rejects an over-cap batch outright, so sending the lot would
  // delete nothing and leave unchecking rows by hand as the only way out — on
  // exactly the oversized KBs this feature exists for.
  it('splits a selection larger than the cap, losing nothing', () => {
    const ids = Array.from({ length: 2500 }, (_, i) => `m-${i}`)
    const batches = chunkForBulkDelete(ids)

    expect(batches.map(b => b.length)).toEqual([BULK_DELETE_BATCH, 500])
    expect(batches.flat()).toEqual(ids)
  })

  it('sends one request when the selection fits', () => {
    const ids = ['a', 'b', 'c']
    expect(chunkForBulkDelete(ids)).toEqual([ids])
  })

  it('sends nothing for an empty selection', () => {
    expect(chunkForBulkDelete([])).toEqual([])
  })

  it('divides evenly without emitting a trailing empty batch', () => {
    const ids = Array.from({ length: 8 }, (_, i) => `x-${i}`)
    expect(chunkForBulkDelete(ids, 4).map(b => b.length)).toEqual([4, 4])
  })
})

describe('KBTestQueriesTab filter reset', () => {
  beforeEach(() => generateKBTestQueriesAndWait.mockClear())

  it('returns to "All" after generating, so the new rows are visible', async () => {
    // Generation reports nothing on success. Left on the user-authored slice
    // it renders no new row and reads as a silent failure, which invites a
    // re-run and a duplicate batch.
    renderTab()

    fireEvent.click(screen.getByRole('button', { name: /^User-authored/ }))
    await waitFor(() => {
      expect(screen.queryByText('Generated question A?')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Auto-generate \(LLM\)/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'confirm-generate' }))
    await waitFor(() => expect(generateKBTestQueriesAndWait).toHaveBeenCalled())
    await waitFor(() => {
      expect(screen.getByText('Generated question A?')).toBeInTheDocument()
    })
  })
})

describe('KBTestQueriesTab delete confirmation', () => {
  beforeEach(() => confirmFn.mockClear())

  it('does not promise that validation exports keep the expected answer', async () => {
    // ValidationRun carries no test_query_snapshot; the export re-joins the
    // live set for expected_answer and external_id, so a pruned question
    // exports blank. That is the wrong thing to be confidently wrong about
    // immediately before an irreversible action.
    renderTab()

    fireEvent.click(screen.getByLabelText(/^Select all/))
    fireEvent.click(screen.getByRole('button', { name: /Delete selected/ }))

    await waitFor(() => expect(confirmFn).toHaveBeenCalled())
    const { message } = confirmFn.mock.calls[0][0]
    expect(message).not.toMatch(/keep their own copy/i)
    expect(message).toMatch(/blank expected answer/i)
  })
})
