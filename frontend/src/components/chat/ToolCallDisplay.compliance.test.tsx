import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// check_compliance reports all_compliant: null when a rule couldn't be
// evaluated or a requested document wasn't read. That used to read "All 1
// document compliant" because the summary only checked for violations (#1013).
const call = { tool_name: 'check_compliance', tool_call_id: 'cc-1', args: { document_uuids: ['d1'] } }
const checked = (content: unknown) => ({ tool_name: 'check_compliance', tool_call_id: 'cc-1', content, quality: null })

describe('compliance check summary', () => {
  it('shows an unconfirmed result as inconclusive, not compliant', () => {
    render(<ToolStatusLine call={call} result={checked({
      rules_checked: 1, documents_checked: 1, all_compliant: null, outcome: 'inconclusive', total_violations: 0,
    })} />)
    expect(screen.getByText('Inconclusive: not every rule could be confirmed')).toBeInTheDocument()
    expect(screen.queryByText(/compliant$/)).toBeNull()
  })

  it('still reports a confirmed pass', () => {
    render(<ToolStatusLine call={call} result={checked({
      rules_checked: 1, documents_checked: 2, all_compliant: true, outcome: 'pass', total_violations: 0,
    })} />)
    expect(screen.getByText('Configured rules passed for 2 documents')).toBeInTheDocument()
    expect(screen.queryByText(/documents compliant/)).toBeNull()
  })

  it('still counts violations', () => {
    render(<ToolStatusLine call={call} result={checked({
      rules_checked: 2, documents_checked: 1, all_compliant: false, outcome: 'fail', total_violations: 1,
    })} />)
    expect(screen.getByText('1 violation across 1 document')).toBeInTheDocument()
  })
})
