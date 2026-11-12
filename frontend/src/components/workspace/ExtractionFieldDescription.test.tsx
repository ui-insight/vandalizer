import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { DesignTab } from './ExtractionEditorPanel'

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))

const props = (onUpdateItem = vi.fn()) => ({
  onAddFields: vi.fn(async () => {}), onOpenTools: vi.fn(), onValidate: vi.fn(),
  items: [{ id: 'i1', searchphrase: 'Total Direct Costs', is_optional: false, enum_values: [], description: 'Also labelled Direct-cost total.' }],
  itemsLoading: false, results: {}, hasResults: false, running: false,
  config: {} as React.ComponentProps<typeof DesignTab>['config'], docCount: 0,
  onExportCSV: vi.fn(), onExportJSON: vi.fn(), onExportCopy: vi.fn(),
  onRemoveItem: vi.fn(), onUpdateItem, onReorder: vi.fn(), onValueClick: vi.fn(),
  sources: {}, crossField: null, documentWarnings: [], resultSets: [], resultDocNames: [],
  activeResultIdx: 0, onSetActiveResultIdx: vi.fn(),
})

describe('Extraction field description (#1057)', () => {
  it('shows the saved description and saves an edit without renaming the field', () => {
    const onUpdateItem = vi.fn()
    render(<DesignTab {...props(onUpdateItem)} />)
    fireEvent.click(screen.getByRole('button', { name: /Total Direct Costs/ }))
    const box = screen.getByRole('textbox', { name: 'Meaning and other labels' })
    expect(box).toHaveValue('Also labelled Direct-cost total.')
    fireEvent.change(box, { target: { value: '  Also labelled Direct-cost total or TDC.  ' } })
    fireEvent.blur(box)
    expect(onUpdateItem).toHaveBeenCalledWith('i1', { description: 'Also labelled Direct-cost total or TDC.' })
  }, 60000)

  it('does not save when nothing changed', () => {
    const onUpdateItem = vi.fn()
    render(<DesignTab {...props(onUpdateItem)} />)
    fireEvent.click(screen.getByRole('button', { name: /Total Direct Costs/ }))
    fireEvent.blur(screen.getByRole('textbox', { name: 'Meaning and other labels' }))
    expect(onUpdateItem).not.toHaveBeenCalled()
  }, 60000)
})
