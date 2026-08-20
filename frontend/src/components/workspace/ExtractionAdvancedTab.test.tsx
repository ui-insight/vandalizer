import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AdvancedTab } from './ExtractionEditorPanel'

const baseProps = {
  config: {},
  useDefaults: true,
  onSetUseDefaults: () => {},
  onSaveConfig: () => {},
  searchSetUuid: 'ss-123',
  hasFields: true,
  onExportDefinition: () => {},
  onImportDefinition: () => {},
}

const card = (title: string) => screen.getByText(title).closest('[role="button"]') as HTMLElement

describe('AdvancedTab with no fields', () => {
  it('disables Export Definition and says why', () => {
    render(<AdvancedTab {...baseProps} hasFields={false} />)
    const exportCard = card('Export Definition')
    expect(exportCard.getAttribute('aria-disabled')).toBe('true')
    expect(exportCard.getAttribute('tabindex')).toBe('-1')
    expect(screen.getByText(/there is nothing to export yet/)).toBeTruthy()
  })

  it('does not export on click or keypress', () => {
    const onExportDefinition = vi.fn()
    render(<AdvancedTab {...baseProps} hasFields={false} onExportDefinition={onExportDefinition} />)
    fireEvent.click(card('Export Definition'))
    fireEvent.keyDown(card('Export Definition'), { key: 'Enter' })
    expect(onExportDefinition).not.toHaveBeenCalled()
  })

  it('keeps Import Definition available', () => {
    const onImportDefinition = vi.fn()
    render(<AdvancedTab {...baseProps} hasFields={false} onImportDefinition={onImportDefinition} />)
    expect(card('Import Definition').getAttribute('aria-disabled')).toBeNull()
    fireEvent.click(card('Import Definition'))
    expect(onImportDefinition).toHaveBeenCalledOnce()
  })

  it('keeps Extraction Settings available', () => {
    const onSetUseDefaults = vi.fn()
    render(<AdvancedTab {...baseProps} hasFields={false} onSetUseDefaults={onSetUseDefaults} />)
    expect(screen.getByText('Extraction Settings')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(onSetUseDefaults).toHaveBeenCalledWith(false)
  })

  it('replaces the API snippets with a note that fields are required', () => {
    render(<AdvancedTab {...baseProps} hasFields={false} />)
    expect(screen.getByText('Run this extraction via API')).toBeTruthy()
    expect(screen.getByText(/Add at least one field/)).toBeTruthy()
    // No endpoint or copyable examples for a call that would come back empty.
    expect(screen.queryByText('Endpoint')).toBeNull()
    expect(screen.queryByText('Python')).toBeNull()
    expect(screen.queryByText('cURL')).toBeNull()
    expect(screen.queryByText('ss-123')).toBeNull()
  })
})

describe('AdvancedTab with fields', () => {
  it('enables Export Definition', () => {
    const onExportDefinition = vi.fn()
    render(<AdvancedTab {...baseProps} onExportDefinition={onExportDefinition} />)
    const exportCard = card('Export Definition')
    expect(exportCard.getAttribute('aria-disabled')).toBeNull()
    fireEvent.click(exportCard)
    expect(onExportDefinition).toHaveBeenCalledOnce()
    expect(screen.getByText('Download as a shareable JSON file')).toBeTruthy()
  })

  it('shows the full API section', () => {
    render(<AdvancedTab {...baseProps} />)
    expect(screen.getByText('Endpoint')).toBeTruthy()
    expect(screen.getByText('Python')).toBeTruthy()
    expect(screen.getByText('cURL')).toBeTruthy()
    expect(screen.getByText('ss-123')).toBeTruthy()
    expect(screen.queryByText(/Add at least one field/)).toBeNull()
  })
})
