import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExpandableValue, formatExtractedValue } from './extractionValue'
import { ToolCallDisplay } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflow: vi.fn() }) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../api/workflows', () => ({ getWorkflowStatus: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// Support ticket: NIH R01 Extraction from chat showed Key Personnel Role as
// `["PI","Co-Investigator",…,"Graduate Stu...` with no way to read the rest.
const roles = '["PI","Co-Investigator","Co-Investigator","Postdoctoral Researcher","Research Coordinator","Graduate Student"]'

describe('formatExtractedValue', () => {
  it.each([
    [roles, 'PI, Co-Investigator, Co-Investigator, Postdoctoral Researcher, Research Coordinator, Graduate Student'],
    [['Dr. James Park', 'Dr. Lisa Yamamoto'], 'Dr. James Park, Dr. Lisa Yamamoto'],
    ['{"year": 1, "amount": "$304,000"}', 'year: 1; amount: $304,000'],
    ['[not json', '[not json'],
    ['Brackets [like this] stay', 'Brackets [like this] stay'],
    [42, '42'],
    ['[]', ''],
  ])('reads %j as %j', (value, text) => {
    expect(formatExtractedValue(value)).toBe(text)
  })
})

describe('ExpandableValue', () => {
  it('shows a long value in full on request', () => {
    const long = 'The project will characterize hippocampal circuit dynamics '.repeat(5)
    render(<ExpandableValue value={long} />)
    expect(screen.queryByText(long.trim())).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(screen.getByText(long.trim(), { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('offers nothing to expand on a short value', () => {
    render(<ExpandableValue value="R01NS012345" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('chat extraction field list', () => {
  it('shows a list field as readable text, whole', () => {
    const content = {
      extraction_set: 'NIH R01 Extraction',
      fields: ['Key Personnel Role'],
      entities: [{ 'Key Personnel Role': roles }],
    }
    render(
      <ToolCallDisplay
        toolCalls={[{ tool_name: 'run_extraction', tool_call_id: 'x-1', args: {} }]}
        toolResults={[{ tool_name: 'run_extraction', tool_call_id: 'x-1', content, quality: null }]}
        isStreaming={false}
      />,
    )
    const text = 'PI, Co-Investigator, Co-Investigator, Postdoctoral Researcher, Research Coordinator, Graduate Student'
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.queryByText(/\["PI"/)).toBeNull()
  })
})
