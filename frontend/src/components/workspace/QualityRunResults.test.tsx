import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QualityRunResults } from './QualityRunResults'
import { getExtractionQualityRunResults } from '../../api/extractions'

vi.mock('../../api/extractions', () => ({ getExtractionQualityRunResults: vi.fn() }))

const field = (field_name: string, expected: string | null, value: string | null, accuracy: number | null) => ({
  field_name, expected, most_common_value: value, accuracy, consistency: 1, replicates: [{ run: 1, value }],
})

beforeEach(() => { vi.clearAllMocks() })

describe('QualityRunResults', () => {
  it('shows which fields matched and which missed (ticket)', async () => {
    vi.mocked(getExtractionQualityRunResults).mockResolvedValue({
      documents: [{
        test_case_uuid: 'tc-1', label: 'NSF Subaward UI-BSU-2024-0847', overall_accuracy: 0.5,
        fields: [field('FAIN', '2024-0847', '2024-0847', 1), field('Cost Share', '$5,000', null, 0), field('PI', 'Lee', 'Lee', 0.5)],
      }],
    })
    render(<QualityRunResults searchSetUuid="ss-1" runUuid="run-1" />)
    expect(await screen.findByText('NSF Subaward UI-BSU-2024-0847')).toBeInTheDocument()
    expect(getExtractionQualityRunResults).toHaveBeenCalledWith('ss-1', 'run-1')
    expect(screen.getByText('Matched')).toBeInTheDocument()
    expect(screen.getByText('Missed')).toBeInTheDocument()
    expect(screen.getByText('Matched 50% of runs')).toBeInTheDocument()
    expect(screen.getByText('$5,000')).toBeInTheDocument()
    expect(screen.getByText('(empty)')).toBeInTheDocument()
  })

  it('says so when the run saved no field results', async () => {
    vi.mocked(getExtractionQualityRunResults).mockResolvedValue({ documents: [] })
    render(<QualityRunResults searchSetUuid="ss-1" runUuid="run-1" />)
    expect(await screen.findByText('This run saved no per-field results.')).toBeInTheDocument()
  })

  it('reports a failed load', async () => {
    vi.mocked(getExtractionQualityRunResults).mockRejectedValue(new Error('500'))
    render(<QualityRunResults searchSetUuid="ss-1" runUuid="run-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent("Could not load this run's field results.")
  })
})
