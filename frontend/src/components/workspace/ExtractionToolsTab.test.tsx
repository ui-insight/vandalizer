import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ToolsTab } from './ExtractionEditorPanel'

const baseProps = {
  onClone: vi.fn(),
  onDelete: vi.fn(),
  onAttachTemplate: vi.fn(),
  onGenerateTemplate: vi.fn(),
  onExportPdf: vi.fn(),
  onBuildFromDocument: vi.fn(),
  buildingFromDoc: false,
  attachingTemplate: false,
  templateError: null as string | null,
  generatingTemplate: false,
  exportingPdf: false,
  hasDocuments: true,
  hasResults: false,
  hasTemplate: false,
  hasItems: true,
}

// Timeouts are generous: importing the extraction editor module is slow enough
// under jsdom that the first test in the file pays for it.
describe('ToolsTab template attachment', () => {
  it('reports a failed attachment instead of leaving the card silent', () => {
    const { rerender } = render(
      <ToolsTab
        {...baseProps}
        templateError="This PDF has no form fields, so there is nothing to build extraction fields from."
      />,
    )
    expect(screen.getByRole('alert').textContent).toMatch(/no form fields/i)

    // …and says nothing when the last attachment didn't fail.
    rerender(<ToolsTab {...baseProps} />)
    expect(screen.queryByRole('alert')).toBeNull()
  }, 60000)

  it('distinguishes Attach Template from From Document', () => {
    render(<ToolsTab {...baseProps} />)

    // Attach Template states its precondition; From Document states it has none.
    expect(screen.getByText(/one with form fields in it/i)).toBeTruthy()
    expect(screen.getByText(/works with any document/i)).toBeTruthy()
  }, 30000)
})
