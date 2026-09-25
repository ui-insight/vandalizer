import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DocumentUsageDialog, summarizeUsage, describeWorkflowUse, mergeUsage, describeDeleteEffects, UsageSummaryList, RemoveFromKnowledgeBasesOption } from './DocumentUsageDialog'
import { fetchDocumentUsage, type DocumentUsage } from '../../api/files'

vi.mock('../../api/files', () => ({
  fetchDocumentUsage: vi.fn(),
}))

const USAGE: DocumentUsage = {
  document: { uuid: 'd1', title: 'Award.pdf' },
  folder: { path: [{ uuid: 'f1', title: 'Grants' }, { uuid: 'f2', title: 'FY26' }], team_id: null },
  knowledge_bases: [{ uuid: 'kb1', title: 'Sponsor policies', exists: true }],
  extractions: [{ uuid: 'ss1', title: 'Budget fields', exists: true, test_cases: [{ uuid: 'tc1', label: 'NSF case' }] }],
  workflows: [{ id: 'w1', name: 'Award review', uses: [{ kind: 'fixed_document' }, { kind: 'step_document', step: 'Summarize', task: 'Prompt', role: 'selected document' }] }],
  total: 3,
}

describe('summarizeUsage', () => {
  it('joins the non-empty sections into one sentence', () => {
    expect(summarizeUsage(USAGE)).toBe('used in 1 knowledge base, 1 extraction and 1 workflow')
    expect(summarizeUsage({ ...USAGE, extractions: [], workflows: [] })).toBe('used in 1 knowledge base')
    expect(summarizeUsage({ knowledge_bases: [], extractions: [], workflows: [] }))
      .toBe('not used in any knowledge base, extraction or workflow')
  })
})

describe('mergeUsage', () => {
  it('de-duplicates references shared by several documents and combines their details', () => {
    const second: DocumentUsage = {
      ...USAGE,
      document: { uuid: 'd2', title: 'Budget.xlsx' },
      knowledge_bases: [{ uuid: 'kb1', title: 'Sponsor policies', exists: true }, { uuid: 'kb2', title: 'Rates', exists: true }],
      extractions: [{ uuid: 'ss1', title: 'Budget fields', exists: true, test_cases: [{ uuid: 'tc1', label: 'NSF case' }, { uuid: 'tc2', label: 'NIH case' }] }],
      workflows: [{ id: 'w1', name: 'Award review', uses: [{ kind: 'fixed_document' }] }],
      total: 4,
    }
    const merged = mergeUsage([USAGE, second])
    expect(merged.knowledge_bases.map(kb => kb.uuid)).toEqual(['kb1', 'kb2'])
    expect(merged.extractions).toHaveLength(1)
    expect(merged.extractions[0].test_cases.map(tc => tc.label)).toEqual(['NSF case', 'NIH case'])
    expect(merged.workflows).toHaveLength(1)
    expect(merged.workflows[0].uses).toHaveLength(2)
    expect(merged.total).toBe(4)
    expect(summarizeUsage(merged)).toBe('used in 2 knowledge bases, 1 extraction and 1 workflow')
  })

  it('is empty for no documents', () => {
    expect(mergeUsage([])).toEqual({ knowledge_bases: [], extractions: [], workflows: [], total: 0 })
  })
})

describe('describeWorkflowUse', () => {
  it('names the role and step', () => {
    expect(describeWorkflowUse({ kind: 'fixed_document' })).toBe('fixed document (Input tab)')
    expect(describeWorkflowUse({ kind: 'step_document', step: 'Fill', task: 'FormFiller', role: 'form template' }))
      .toBe('form template in step "Fill"')
  })
})

describe('DocumentUsageDialog', () => {
  beforeEach(() => {
    vi.mocked(fetchDocumentUsage).mockReset()
  })

  it('lists location, knowledge bases, extractions and workflows with links', async () => {
    vi.mocked(fetchDocumentUsage).mockResolvedValue(USAGE)
    const onOpenWorkflow = vi.fn()
    const onOpenKnowledgeBase = vi.fn()
    const onClose = vi.fn()
    render(
      <DocumentUsageDialog
        docUuid="d1" docTitle="Award.pdf" onClose={onClose}
        onOpenWorkflow={onOpenWorkflow} onOpenKnowledgeBase={onOpenKnowledgeBase} onOpenExtraction={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByText(/used in 1 knowledge base, 1 extraction and 1 workflow/)).toBeInTheDocument())
    expect(fetchDocumentUsage).toHaveBeenCalledWith('d1')
    expect(screen.getByText('Grants')).toBeInTheDocument()
    expect(screen.getByText('FY26')).toBeInTheDocument()
    expect(screen.getByText(/NSF case/)).toBeInTheDocument()
    expect(screen.getByText(/fixed document \(Input tab\); selected document in step "Summarize"/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Award review' }))
    expect(onOpenWorkflow).toHaveBeenCalledWith('w1')
    expect(onClose).toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Sponsor policies' }))
    expect(onOpenKnowledgeBase).toHaveBeenCalledWith('kb1', 'Sponsor policies')
  })

  it('says plainly when nothing references the document', async () => {
    vi.mocked(fetchDocumentUsage).mockResolvedValue({
      ...USAGE, knowledge_bases: [], extractions: [], workflows: [], total: 0,
    })
    render(<DocumentUsageDialog docUuid="d1" docTitle="Award.pdf" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/Deleting it will not affect anything else/)).toBeInTheDocument())
    expect(screen.getAllByText('None')).toHaveLength(3)
  })

  it('shows the error when the lookup fails', async () => {
    vi.mocked(fetchDocumentUsage).mockRejectedValue(new Error('Document not found'))
    render(<DocumentUsageDialog docUuid="d1" docTitle="Award.pdf" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Document not found'))
  })

  it('closes on Escape and on the Close button', async () => {
    vi.mocked(fetchDocumentUsage).mockResolvedValue(USAGE)
    const onClose = vi.fn()
    render(<DocumentUsageDialog docUuid="d1" docTitle="Award.pdf" onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

// Support ticket: the delete dialog promised the file would be removed from
// its knowledge bases, but a KB answers from its own copy and kept answering.
describe('describeDeleteEffects', () => {
  it('says knowledge bases keep their copy — never that deleting removes it', () => {
    const text = describeDeleteEffects(USAGE)
    expect(text).toMatch(/Knowledge bases keep their own copy of it and keep answering from it\./)
    expect(text).toMatch(/Extraction test cases keep a saved snapshot\./)
    expect(text).toMatch(/A workflow that pins it will fail/)
    expect(text).not.toMatch(/removes? it from each/)
  })

  it('points at the removal option when the dialog offers it', () => {
    expect(describeDeleteEffects(USAGE, { removeOffered: true })).toMatch(/unless you remove it below/)
    expect(describeDeleteEffects(USAGE, { many: true })).toMatch(/copy of them.*pins one/)
  })

  it('omits sections with no references', () => {
    expect(describeDeleteEffects({ ...USAGE, extractions: [], workflows: [] }))
      .toBe('Knowledge bases keep their own copy of it and keep answering from it.')
  })
})

describe('UsageSummaryList', () => {
  it('leads with the kind and quotes the name, so a KB named like a file list reads as one KB', () => {
    render(<UsageSummaryList usage={{ ...USAGE, knowledge_bases: [{ uuid: 'kb1', title: 'NSF_PAPPG.pdf (and 1 more)', exists: true }] }} />)
    const kbRow = screen.getByText('“NSF_PAPPG.pdf (and 1 more)”').closest('li')!
    expect(kbRow.textContent).toBe('Knowledge base “NSF_PAPPG.pdf (and 1 more)”')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })
})

describe('RemoveFromKnowledgeBasesOption', () => {
  it('is checked by default and reports changes', () => {
    const onChange = vi.fn()
    render(<RemoveFromKnowledgeBasesOption count={1} onChange={onChange} />)
    const box = screen.getByRole('checkbox', { name: 'Also remove from this knowledge base' })
    expect(box).toBeChecked()
    fireEvent.click(box)
    expect(onChange).toHaveBeenCalledWith(false)
  })

  it('names the count when there are several', () => {
    render(<RemoveFromKnowledgeBasesOption count={2} onChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: 'Also remove from these 2 knowledge bases' })).toBeInTheDocument()
  })
})
