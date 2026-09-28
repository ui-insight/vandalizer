import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CatalogEvidence, validationDate } from './CatalogSignals'
import type { VerifiedCatalogItem } from '../../types/library'
const item = { quality_score: 0, quality_asserted: false, last_validated_at: '2026-09-01T10:00:00Z', test_case_count: 12, validation_run_count: 1 } as VerifiedCatalogItem

describe('catalog evidence', () => {
  it('distinguishes a measured zero from missing quality', () => {
    const { rerender } = render(<CatalogEvidence item={item} />)
    expect(screen.getByText('Recorded validation score')).toBeTruthy()
    expect(screen.getByText('12 test cases')).toBeTruthy()
    expect(screen.getByText('Sep 1, 2026')).toBeTruthy()
    rerender(<CatalogEvidence item={{ ...item, quality_score: null, last_validated_at: null }} />)
    expect(screen.getByText('No measured score available')).toBeTruthy()
    expect(screen.getByText('Not recorded')).toBeTruthy()
  })
  it('identifies asserted ratings and regression limitations', () => {
    render(<CatalogEvidence item={{ ...item, quality_asserted: true, regression_pending_review: true }} />)
    expect(screen.getByText('Author-provided rating; not measured here')).toBeTruthy()
    expect(screen.queryByText('12 test cases')).toBeNull()
    expect(screen.getByText(/A regression is awaiting review/)).toBeTruthy()
    expect(validationDate('invalid')).toBeNull()
  })
})
